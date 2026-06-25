# Sistema de Monitoramento Industrial — QuantumFinance
# Raspberry Pi Pico W + SSD1306 OLED + Potenciômetro + Botões
#
# Hardware:
#   I2C1 (GP14=SDA, GP15=SCL) → SSD1306 OLED 128×64
#   GP26 (ADC0)               → Potenciômetro = temperatura simulada (20–120°C)
#   GP2                       → Botão PESSOA (pull-up; pressionar = pessoa na zona)
#   GP3                       → Botão RESET alertas (pull-up)
#   GP6                       → LED verde  (SEGURO)
#   GP7                       → LED vermelho (ALERTA)
#   GP8                       → LED amarelo  (AVISO)

import machine, utime, json
from machine import Pin, I2C, ADC
import ssd1306

# ─── OLED ─────────────────────────────────────────────────────────────────
i2c_oled = I2C(1, sda=Pin(14), scl=Pin(15), freq=400000)
oled = None
try:
    oled = ssd1306.SSD1306_I2C(128, 64, i2c_oled)
    print("OLED: OK")
except Exception as e:
    print("OLED ERRO:", e)

# ─── Pinos de saída ────────────────────────────────────────────────────────
LED_OK    = Pin(6, Pin.OUT)
LED_ALERT = Pin(7, Pin.OUT)
LED_WARN  = Pin(8, Pin.OUT)

# ─── Botões com IRQ ───────────────────────────────────────────────────────
BTN_PESSOA = Pin(2, Pin.IN, Pin.PULL_UP)
BTN_RESET  = Pin(3, Pin.IN, Pin.PULL_UP)

# Flags de interrupção — captura qualquer press, mesmo rápido
_flag_pessoa = False
_flag_reset  = False

def irq_pessoa(pin):
    global _flag_pessoa
    _flag_pessoa = True

def irq_reset(pin):
    global _flag_reset
    _flag_reset = True

BTN_PESSOA.irq(trigger=Pin.IRQ_FALLING, handler=irq_pessoa)
BTN_RESET.irq(trigger=Pin.IRQ_FALLING,  handler=irq_reset)

# ─── ADC temperatura ──────────────────────────────────────────────────────
adc_temp = ADC(Pin(26))

# ─── Configurações ────────────────────────────────────────────────────────
PLANTA_ID     = "SP01"
AREA_NOME     = "FORNO_A"
TEMP_LIMITE   = 80.0   # °C
PESSOA_LIMITE = 10     # segundos

# ─── Estado ───────────────────────────────────────────────────────────────
estado       = "SEGURO"
alertas      = 0
tick         = 0
pessoa_seg   = 0
pessoa_ativa = False   # True enquanto botão pressionado ou IRQ ativo

# ─── Funções ──────────────────────────────────────────────────────────────
def ler_temp():
    raw = adc_temp.read_u16()
    return round(20.0 + (raw / 65535.0) * 100.0, 1)

def set_leds(ok, warn, alert):
    LED_OK.value(ok)
    LED_WARN.value(warn)
    LED_ALERT.value(alert)

def atualizar_oled(temp, p_seg, est):
    if oled is None:
        return
    oled.fill(0)

    # Linha 0 — título + tick
    oled.text("MONIT.INDUSTR", 0, 0)
    oled.text("t={:04d}".format(tick), 88, 0)

    # Linha 1 — estado
    if est == "SEGURO":
        oled.text("{} OK".format(AREA_NOME), 0, 10)
    elif est == "AVISO":
        oled.text("{} AVISO".format(AREA_NOME), 0, 10)
    else:
        oled.text("!! ALERTA !!", 14, 10)

    # Linha 2 — temperatura
    oled.text("TEMP:{:.1f}C".format(temp), 0, 22)
    if temp >= TEMP_LIMITE:
        oled.text("LIMITE!", 80, 22)

    # Linha 3 — pessoa
    if not pessoa_ativa:
        oled.text("ZONA: livre", 0, 33)
    elif p_seg <= PESSOA_LIMITE:
        oled.text("ZONA:{:02d}s/{:02d}s".format(p_seg, PESSOA_LIMITE), 0, 33)
    else:
        oled.text("EVACUACAO!{:02d}s".format(p_seg), 0, 33)

    # Barra temperatura
    bw = int(126 * min(temp / 120.0, 1.0))
    oled.rect(0, 44, 128, 8, 1)
    if bw > 0:
        oled.fill_rect(1, 45, bw, 6, 1)

    # Linha final
    oled.text("ALERTAS:{}".format(alertas), 0, 55)
    oled.show()

# ─── Startup ──────────────────────────────────────────────────────────────
print("=== MONITORAMENTO INDUSTRIAL — QuantumFinance ===")
print("Planta:{} | Area:{} | Temp max:{}C | Tempo max:{}s".format(
    PLANTA_ID, AREA_NOME, TEMP_LIMITE, PESSOA_LIMITE))
print("GP2(botao) = PESSOA NA ZONA | GP3(botao) = RESET")
print("GP26(pot)  = TEMPERATURA (gire para subir)")
print("---")

if oled:
    oled.fill(0)
    oled.text("QUANTUMFINANCE", 8, 10)
    oled.text("Monit.Industrial", 0, 26)
    oled.text("Iniciando...", 22, 42)
    oled.show()
    utime.sleep_ms(1200)

# ─── Loop principal (250ms por ciclo, responsivo) ─────────────────────────
prev_alerta = False
ciclo = 0

while True:
    global _flag_pessoa, _flag_reset

    temp         = ler_temp()
    btn_agora    = not BTN_PESSOA.value()   # True se pressionado agora
    reset_agora  = not BTN_RESET.value()

    # Detecta pessoa (IRQ OU botão mantido)
    if _flag_pessoa or btn_agora:
        pessoa_ativa = True
        _flag_pessoa = False
    else:
        pessoa_ativa = False
        pessoa_seg = 0

    # Timer de presença (incrementa a cada 4 ciclos de 250ms = 1s)
    if pessoa_ativa and ciclo % 4 == 0:
        pessoa_seg += 1

    # Reset
    if _flag_reset or reset_agora:
        alertas = 0
        pessoa_ativa = False
        pessoa_seg = 0
        estado = "SEGURO"
        _flag_reset = False
        print("RESET: alertas limpos")

    # Determina estado
    alerta_pessoa = pessoa_ativa and pessoa_seg > PESSOA_LIMITE
    alerta_temp   = temp >= TEMP_LIMITE
    novo_alerta   = (alerta_pessoa or alerta_temp) and not prev_alerta

    if alerta_pessoa or alerta_temp:
        estado = "ALERTA"
        if novo_alerta:
            alertas += 1
            print("!! NOVO ALERTA — total:", alertas)
    elif pessoa_ativa:
        estado = "AVISO"
    else:
        estado = "SEGURO"

    prev_alerta = (alerta_pessoa or alerta_temp)

    # LEDs
    if estado == "SEGURO":
        set_leds(1, 0, 0)
    elif estado == "AVISO":
        set_leds(0, 1, 0)
    else:
        set_leds(0, 0, 1)

    # OLED (a cada 4 ciclos = 1s para não sobrecarregar I2C)
    if ciclo % 4 == 0:
        atualizar_oled(temp, pessoa_seg, estado)

    # Telemetria serial (a cada 4 ciclos = 1s)
    if ciclo % 4 == 0:
        print(json.dumps({
            "t":             tick,
            "planta":        PLANTA_ID,
            "area":          AREA_NOME,
            "estado":        estado,
            "temperatura":   temp,
            "alerta_temp":   alerta_temp,
            "pessoa_zona":   pessoa_ativa,
            "pessoa_seg":    pessoa_seg,
            "alerta_pessoa": alerta_pessoa,
            "alertas_total": alertas,
            "mqtt":          "quantumfinance/{}/{}".format(
                                 PLANTA_ID.lower(), AREA_NOME.lower())
        }))
        tick += 1

    ciclo += 1
    utime.sleep_ms(250)   # polling a cada 250ms — botão detectado em < 250ms