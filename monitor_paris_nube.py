"""
Versión para GitHub Actions: revisa UNA vez y termina.
El token y el canal de Telegram vienen de los "secretos" de GitHub (no se escriben aquí).
"""
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

# ---------- CONFIGURACIÓN ----------
DESCUENTO_MINIMO = 70
COMUNA = "13114"
BUSQUEDAS = ["notebook", "televisor", "zapatillas", "celular", "refrigerador", "audifonos"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ARCHIVO_VISTOS = Path("vistos_paris.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

PATRON_PRECIOS = re.compile(
    r'"prices":\{"regular":\{[^{}]*"value":\{[^{}]*"centAmount":(\d+)[^{}]*\}\},'
    r'"offer":\{[^{}]*"value":\{[^{}]*"centAmount":(\d+)[^{}]*\},"discountOnRegular":([\d.eE-]+)\}'
    r'(?:,"paymentMethod":\{[^{}]*"value":\{[^{}]*"centAmount":(\d+)[^{}]*\},"discountOnRegular":([\d.eE-]+))?'
)


def clp(n):
    return "$" + f"{n:,.0f}".replace(",", ".")


def obtener_productos(busqueda):
    url = busqueda if busqueda.startswith("http") else f"https://www.paris.cl/search?q={quote(busqueda)}&commune={COMUNA}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.text.replace('\\"', '"')

    links = {}
    for nombre, link in re.findall(r'"@type":"Product","name":"(.*?)","url":"(.*?)"', html):
        links[nombre.replace("\\", "")] = link

    productos = []
    for m in PATRON_PRECIOS.finditer(html):
        regular, oferta, d_oferta, tarjeta, d_tarjeta = m.groups()
        trozo = html[m.end(): m.end() + 2500]
        alt = re.search(r'"alt":"(.*?)"', trozo)
        nombre = re.sub(r"-\d+$", "", alt.group(1)).replace("\\", "") if alt else "Producto sin nombre"
        link = links.get(nombre) or f"https://www.paris.cl/search?q={quote(nombre)}"
        img = re.search(r'"images":\[\{"url":"(.*?)"', trozo)
        imagen = img.group(1) if img else None
        d_o = float(d_oferta) * 100
        d_t = float(d_tarjeta) * 100 if d_tarjeta else 0
        productos.append({
            "nombre": nombre, "link": link, "imagen": imagen,
            "regular": int(regular), "oferta": int(oferta), "tarjeta": int(tarjeta) if tarjeta else None,
            "desc": max(d_o, d_t), "con_tarjeta": d_t > d_o,
        })
    return productos


def avisar(texto, imagen=None):
    base = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    if imagen:
        try:
            foto = requests.get(imagen, headers=HEADERS, timeout=20)
            foto.raise_for_status()
            r = requests.post(f"{base}/sendPhoto",
                              data={"chat_id": TELEGRAM_CHAT_ID, "caption": texto[:1000]},
                              files={"photo": ("producto.jpg", foto.content)}, timeout=30)
            if r.ok:
                return
            print("Telegram rechazó la foto:", r.text)
        except Exception as e:
            print("No pude bajar la foto:", e)
    requests.post(f"{base}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": texto}, timeout=20)


def mensaje(p):
    extra = f"\nCon Tarjeta Cencosud: {clp(p['tarjeta'])}" if p["con_tarjeta"] else ""
    return (f"🔥 {p['desc']:.0f}% OFF{' (con tarjeta)' if p['con_tarjeta'] else ''}\n{p['nombre']}\n"
            f"Antes {clp(p['regular'])} -> Ahora {clp(p['oferta'])}{extra}\n{p['link']}")


def main():
    vistos = json.loads(ARCHIVO_VISTOS.read_text()) if ARCHIVO_VISTOS.exists() else []
    set_vistos = set(vistos)
    errores = 0
    for b in BUSQUEDAS:
        try:
            productos = obtener_productos(b)
            print(f"[{b}] {len(productos)} productos leídos")
            for p in productos:
                clave = f"{p['nombre']}|{p['oferta']}"
                if p["desc"] >= DESCUENTO_MINIMO and clave not in set_vistos:
                    avisar(mensaje(p), p["imagen"])
                    vistos.append(clave)
                    set_vistos.add(clave)
        except Exception as e:
            errores += 1
            print(f"[{b}] Error:", e)
        time.sleep(3)
    ARCHIVO_VISTOS.write_text(json.dumps(vistos[-3000:]))
    if errores == len(BUSQUEDAS):
        sys.exit(1)  # si todas fallan (por ejemplo, Paris bloquea), GitHub lo marca en rojo


if __name__ == "__main__":
    main()
