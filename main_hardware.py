# Firmware REAL para Raspberry Pi Pico W
# Publica telemetria via MQTT para o Mosquitto Broker
# Configurar: WIFI_SSID, WIFI_PASS, MQTT_BROKER

import network, machine, utime, json
from machine import Pin, I2C, ADC
from umqtt.simple import MQTTClient
import ssd1306

# ─── Configurações Wi-Fi e MQTT ───────────────────────────────────────────
WIFI_SSID   = "SEU_WIFI"
WIFI_PASS   = "SUA_SENHA"
MQTT_BROKER = "192.168.1.100"   # IP do computador com Mosquitto
MQTT_PORT   = 1883
MQTT_TOPIC  = b"quantumfinance/sp01/forno_a"
CLIENT_ID   = b"pico_w_sp01"

# ─── Hardware ─────────────────────────────────────────────────────────────
i2c_oled = I2C(1, sda=Pin(14), scl=Pin(15), freq=400000)
oled = None
try:
    oled = ssd1306.SSD1306_I2C(128, 64, i2c_oled)
except: pass

LED_OK    = Pin(6, Pin.OUT)
LED_ALERT = Pin(7, Pin.OUT)
LED_WARN  = Pin(8, Pin.OUT)

BTN_PESSOA = Pin(2, Pin.IN, Pin.PULL_UP)
BTN_RESET  = Pin(3, Pin.IN, Pin.PULL_UP)
adc_temp   = ADC(Pin(26))

_flag_pessoa = False
_flag_reset  = False

def irq_pessoa(p): global _flag_pessoa; _flag_pessoa = True
def irq_reset(p):  global _flag_reset;  _flag_reset  = True

BTN_PESSOA.irq(trigger=Pin.IRQ_FALLING, handler=irq_pessoa)
BTN_RESET.irq(trigger=Pin.IRQ_FALLING,  handler=irq_reset)

# ─── Configurações da aplicação ───────────────────────────────────────────
PLANTA_ID     = "SP01"
AREA_NOME     = "FORNO_A"
TEMP_LIMITE   = 80.0
PESSOA_LIMITE = 10

# ─── Conectar Wi-Fi ───────────────────────────────────────────────────────
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Conectando Wi-Fi:", WIFI_SSID)
        wlan.connect(WIFI_SSID, WIFI_PASS)
        timeout = 15
        while not wlan.isconnected() and timeout > 0:
            utime.sleep(1); timeout -= 1
    if wlan.isconnected():
        print("Wi-Fi OK:", wlan.ifconfig()[0])
        return True
    print("Wi-Fi FALHOU")
    return False

# ─── Conectar MQTT ────────────────────────────────────────────────────────
mqtt_client = None

def conectar_mqtt():
    global mqtt_client
    try:
        mqtt_client = MQTTClient(CLIENT_ID, MQTT_BROKER, port=MQTT_PORT)
        mqtt_client.connect()
        print("MQTT OK →", MQTT_BROKER)
        return True
    except Exception as e:
        print("MQTT ERRO:", e)
        return False

def publicar(dados):
    global mqtt_client
    try:
        if mqtt_client:
            mqtt_client.publish(MQTT_TOPIC, json.dumps(dados).encode(), qos=1)
    except Exception as e:
        print("Publish ERRO:", e)
        conectar_mqtt()

# ─── Funções de hardware ──────────────────────────────────────────────────
def ler_temp():
    raw = adc_temp.read_u16()
    return round(20.0 + (raw / 65535.0) * 100.0, 1)

def set_leds(ok, warn, alert):
    LED_OK.value(ok); LED_WARN.value(warn); LED_ALERT.value(alert)

def atualizar_oled(temp, p_seg, est):
    if oled is None: return
    oled.fill(0)
    oled.text("MONIT.INDUSTR", 0, 0)
    oled.text("t={:04d}".format(tick), 88, 0)
    if est == "SEGURO":   oled.text("{} OK".format(AREA_NOME), 0, 10)
    elif est == "AVISO":  oled.text("{} AVISO".format(AREA_NOME), 0, 10)
    else:                 oled.text("!! ALERTA !!", 14, 10)
    oled.text("TEMP:{:.1f}C".format(temp), 0, 22)
    if temp >= TEMP_LIMITE: oled.text("LIMITE!", 80, 22)
    if not pessoa_ativa:    oled.text("ZONA: livre", 0, 33)
    elif p_seg <= PESSOA_LIMITE: oled.text("ZONA:{:02d}s/{:02d}s".format(p_seg, PESSOA_LIMITE), 0, 33)
    else:                   oled.text("EVACUACAO!{:02d}s".format(p_seg), 0, 33)
    bw = int(126 * min(temp / 120.0, 1.0))
    oled.rect(0, 44, 128, 8, 1)
    if bw > 0: oled.fill_rect(1, 45, bw, 6, 1)
    oled.text("ALERTAS:{} MQTT:OK".format(alertas), 0, 55)
    oled.show()

# ─── Inicialização ────────────────────────────────────────────────────────
print("=== QUANTUMFINANCE — Monitoramento Industrial ===")
wifi_ok = conectar_wifi()
mqtt_ok = conectar_mqtt() if wifi_ok else False

estado = "SEGURO"; alertas = 0; tick = 0
pessoa_seg = 0; pessoa_ativa = False
prev_alerta = False; ciclo = 0

# ─── Loop principal ───────────────────────────────────────────────────────
while True:
    global _flag_pessoa, _flag_reset

    temp       = ler_temp()
    btn_agora  = not BTN_PESSOA.value()
    rst_agora  = not BTN_RESET.value()

    if _flag_pessoa or btn_agora:
        pessoa_ativa = True; _flag_pessoa = False
    else:
        pessoa_ativa = False; pessoa_seg = 0

    if pessoa_ativa and ciclo % 4 == 0:
        pessoa_seg += 1

    if _flag_reset or rst_agora:
        alertas = 0; pessoa_ativa = False; pessoa_seg = 0
        estado = "SEGURO"; _flag_reset = False

    alerta_pessoa = pessoa_ativa and pessoa_seg > PESSOA_LIMITE
    alerta_temp   = temp >= TEMP_LIMITE
    novo_alerta   = (alerta_pessoa or alerta_temp) and not prev_alerta

    if alerta_pessoa or alerta_temp:
        estado = "ALERTA"
        if novo_alerta: alertas += 1
    elif pessoa_ativa:
        estado = "AVISO"
    else:
        estado = "SEGURO"

    prev_alerta = (alerta_pessoa or alerta_temp)

    if estado == "SEGURO":   set_leds(1, 0, 0)
    elif estado == "AVISO":  set_leds(0, 1, 0)
    else:                    set_leds(0, 0, 1)

    if ciclo % 4 == 0:
        atualizar_oled(temp, pessoa_seg, estado)
        dados = {
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
        }
        publicar(dados)        # publica no Mosquitto → Node-RED → InfluxDB
        print(json.dumps(dados))
        tick += 1

    ciclo += 1
    utime.sleep_ms(250)