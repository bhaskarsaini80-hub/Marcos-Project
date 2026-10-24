import os
import re
import time
import json
import base64
from datetime import datetime, timezone
import zoneinfo
from io import BytesIO
import xml.etree.ElementTree as ET
from flask import Flask, request, jsonify, send_file, render_template, render_template_string
from playwright.sync_api import sync_playwright

try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False

app = Flask(__name__)

# --- INSTALLATION TIME TRACKER LOGIC ---
INSTALL_RECORD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "install_record.json")

def get_or_create_install_time():
    now = datetime.now()
    if os.path.exists(INSTALL_RECORD_FILE):
        try:
            with open(INSTALL_RECORD_FILE, "r") as f:
                data = json.load(f)
                first_run_str = data.get("first_run")
                first_run_time = datetime.fromisoformat(first_run_str)
        except Exception:
            first_run_time = now
            with open(INSTALL_RECORD_FILE, "w") as f:
                json.dump({"first_run": now.isoformat()}, f)
    else:
        first_run_time = now
        with open(INSTALL_RECORD_FILE, "w") as f:
            json.dump({"first_run": now.isoformat()}, f)
    return first_run_time

# --- HIDDEN WORLD CLOCK LOGIC ---
def get_world_times():
    try:
        py_tz = zoneinfo.ZoneInfo("America/Asuncion")
    except Exception:
        py_tz = timezone.utc

    utc_now = datetime.now(timezone.utc)
    paraguay_now = datetime.now(py_tz)
    local_now = datetime.now()

    return {
        "utc": utc_now.strftime('%Y-%m-%d %H:%M:%S %Z'),
        "paraguay": paraguay_now.strftime('%Y-%m-%d %H:%M:%S %Z'),
        "local": local_now.strftime('%Y-%m-%d %H:%M:%S')
    }

def track_app_installation():
    first_run_time = get_or_create_install_time()
    now = datetime.now()
    diff = now - first_run_time
    days = diff.days
    hours, remainder = divmod(diff.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    world_clock = get_world_times()

    print("=" * 60)
    print(f"🚀 App First Run / Installation Time: {first_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏳ Total Time Elapsed Since First Run: {days} days, {hours} hours, {minutes} minutes, {seconds} seconds")
    print(f"🌍 Hidden World Clock -> Paraguay (Asunción): {world_clock['paraguay']} | UTC: {world_clock['utc']}")
    print("=" * 60)

track_app_installation()
# ---------------------------------------

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

KUDE_PDF_HTML = """
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif; }
    body { color: #0f172a; font-size: 11px; padding: 4mm; background: #fff; }
    .header-box { display: flex; justify-content: space-between; border: 2px solid #0f172a; border-radius: 6px; padding: 10px; margin-bottom: 10px; }
    .emi-col { width: 58%; padding-right: 10px; }
    .emi-title { font-size: 15px; font-weight: bold; text-transform: uppercase; margin-bottom: 4px; }
    .timb-col { width: 40%; border-left: 2px solid #cbd5e1; padding-left: 12px; text-align: right; }
    .doc-badge { display: inline-block; background: #0f172a; color: #fff; font-weight: bold; font-size: 11px; padding: 4px 8px; border-radius: 4px; text-transform: uppercase; margin-bottom: 4px; }
    .inv-no { font-size: 13px; font-weight: bold; color: #1d4ed8; margin-top: 4px; }
    .grid-2 { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
    .info-card { width: 49%; border: 1px solid #cbd5e1; border-radius: 6px; padding: 8px; background: #f8fafc; }
    .card-title { font-size: 9px; font-weight: bold; text-transform: uppercase; color: #64748b; border-bottom: 1px solid #e2e8f0; padding-bottom: 3px; margin-bottom: 5px; }
    .row-line { margin-bottom: 3px; font-size: 10.5px; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
    th { background: #0f172a; color: #fff; font-size: 9.5px; text-transform: uppercase; padding: 6px 5px; border: 1px solid #0f172a; text-align: left; }
    td { font-size: 10px; padding: 6px 5px; border: 1px solid #cbd5e1; }
    .text-right { text-align: right; }
    .font-bold { font-weight: bold; }
    .totals-box { border: 2px solid #0f172a; border-radius: 6px; overflow: hidden; margin-bottom: 10px; }
    .tot-row { display: flex; justify-content: space-between; padding: 6px 10px; border-bottom: 1px solid #e2e8f0; font-size: 10.5px; background: #f8fafc; }
    .tot-final { display: flex; justify-content: space-between; padding: 8px 12px; background: #0f172a; color: #fff; font-size: 13px; font-weight: bold; }
    .footer-box { display: flex; justify-content: space-between; align-items: center; border: 1px solid #cbd5e1; border-radius: 6px; padding: 10px; background: #f8fafc; }
    .cdc-code { font-family: monospace; font-size: 11px; font-weight: bold; letter-spacing: 0.5px; background: #fff; border: 1px solid #cbd5e1; padding: 5px 8px; border-radius: 4px; display: inline-block; margin-top: 4px; }
    .qr-img { width: 85px; height: 85px; border: 1px solid #cbd5e1; padding: 3px; background: #fff; border-radius: 4px; }
  </style>
</head>
<body>
  <div class="header-box">
    <div class="emi-col">
      <div class="emi-title">{{ d.emi_name }}</div>
      <div class="row-line"><strong>Actividad:</strong> {{ d.emi_act }}</div>
      <div class="row-line"><strong>Dirección:</strong> {{ d.emi_dir }} {% if d.emi_ciu %}- {{ d.emi_ciu }}{% endif %}</div>
      <div class="row-line"><strong>Teléfono:</strong> {{ d.emi_tel }} | <strong>Email:</strong> {{ d.emi_email }}</div>
    </div>
    <div class="timb-col">
      <div class="doc-badge">{{ d.doc_type }}</div>
      <div class="row-line"><strong>RUC:</strong> {{ d.emi_ruc }}</div>
      <div class="row-line"><strong>Timbrado N°:</strong> {{ d.timbrado }}</div>
      <div class="row-line"><strong>Inicio Vigencia:</strong> {{ d.fe_ini_t }}</div>
      <div class="inv-no">N° {{ d.invoice_no }}</div>
    </div>
  </div>

  <div class="grid-2">
    <div class="info-card">
      <div class="card-title">Datos del Receptor (Cliente)</div>
      <div class="row-line"><strong>Nombre / Razón:</strong> {{ d.rec_name }}</div>
      <div class="row-line"><strong>RUC / Doc. ID:</strong> {{ d.rec_doc }}</div>
      <div class="row-line"><strong>Dirección:</strong> {{ d.rec_dir }}</div>
      <div class="row-line"><strong>Tel / Email:</strong> {{ d.rec_tel }} {% if d.rec_email != '—' %}| {{ d.rec_email }}{% endif %}</div>
    </div>
    <div class="info-card">
      <div class="card-title">Condiciones de la Operación</div>
      <div class="row-line"><strong>Fecha de Emisión:</strong> {{ d.fe_emi }}</div>
      <div class="row-line"><strong>Condición Venta:</strong> {{ d.cond_ope }} ({{ d.payment_type }})</div>
      <div class="row-line"><strong>Moneda:</strong> {{ d.currency }} {% if d.currency_name %}- {{ d.currency_name }}{% endif %}</div>
      <div class="row-line"><strong>Tipo Transacción:</strong> {{ d.tip_tra }}</div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th style="width:8%">Cód.</th>
        <th style="width:34%">Descripción Producto / Servicio</th>
        <th style="width:7%">Unid.</th>
        <th class="text-right" style="width:8%">Cant.</th>
        <th class="text-right" style="width:12%">Precio Unit.</th>
        <th class="text-right" style="width:9%">Desc.</th>
        <th class="text-right" style="width:10%">Exentas</th>
        <th class="text-right" style="width:12%">Subtotal</th>
      </tr>
    </thead>
    <tbody>
      {% for item in d['items'] %}
      <tr>
        <td>{{ item.code }}</td>
        <td class="font-bold">{{ item.desc }}</td>
        <td>{{ item.unit }}</td>
        <td class="text-right">{{ item.qty }}</td>
        <td class="text-right">{{ item.price }}</td>
        <td class="text-right">{{ item.discount }}</td>
        <td class="text-right">{{ item.exenta }}</td>
        <td class="text-right font-bold">{{ item.subtotal }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <div class="totals-box">
    <div class="tot-row">
      <span><strong>Subtotales:</strong> Exentas: {{ d.sub_exe }} | Gravadas 5%: {{ d.sub_5 }} | Gravadas 10%: {{ d.sub_10 }}</span>
      <span><strong>Total Descuento:</strong> {{ d.tot_desc }} {{ d.currency }}</span>
    </div>
    <div class="tot-row" style="background:#fff;">
      <span><strong>Liquidación del IVA:</strong> (5%): {{ d.iva_5 }} | (10%): {{ d.iva_10 }} | <strong>Total IVA: {{ d.tot_iva }} {{ d.currency }}</strong></span>
    </div>
    <div class="tot-final">
      <span>TOTAL GENERAL DE LA OPERACIÓN ({{ d.currency }})</span>
      <span>{{ d.tot_gral }} {{ d.currency }}</span>
    </div>
  </div>

  <div class="footer-box">
    <div style="width: 80%;">
      <div class="font-bold" style="font-size:11px;">KuDE - Representación Gráfica de Documento Electrónico (SIFEN / DNIT)</div>
      <div style="font-size:10px; color:#475569; margin-top:2px;">Consulte la validez de esta Factura Electrónica con el número de CDC en: <strong>https://ekuatia.set.gov.py/consultas/</strong></div>
      <div style="font-size:10px; font-weight:bold; margin-top:5px;">CDC (Código de Control - 44 dígitos):</div>
      <div class="cdc-code">{{ d.cdc_formatted }}</div>
    </div>
    {% if d.qr_img %}
    <img src="{{ d.qr_img }}" class="qr-img" alt="QR" />
    {% endif %}
  </div>
</body>
</html>
"""

def strip_ns(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag

def find_text(elem, tag_name, default=""):
    if elem is None:
        return default
    for child in elem.iter():
        if strip_ns(child.tag) == tag_name and child.text and child.text.strip():
            return child.text.strip()
    return default

def find_node(root, tag_name):
    for child in root.iter():
        if strip_ns(child.tag) == tag_name:
            return child
    return None

def find_all_nodes(root, tag_name):
    return [child for child in root.iter() if strip_ns(child.tag) == tag_name]

def fmt_num(val, currency="PYG"):
    if val is None or str(val).strip() == "":
        return "0"
    try:
        num = float(str(val).strip())
        if currency == "PYG" or num.is_integer():
            return f"{int(round(num)):,}".replace(",", ".")
        return f"{num:,.2f}"
    except Exception:
        return str(val)

def fmt_date(val):
    return str(val).replace("T", " ") if val else "—"

def fmt_cdc(cdc):
    clean = re.sub(r"\s+", "", str(cdc or ""))
    return " ".join(clean[i:i+4] for i in range(0, len(clean), 4))

def make_qr_base64(qr_url):
    if not qr_url or not HAS_QR:
        return ""
    qr = qrcode.QRCode(version=1, box_size=4, border=1)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

def parse_essential_sifen_xml(xml_bytes):
    root = ET.fromstring(xml_bytes)
    de_node = find_node(root, "DE")
    cdc = de_node.attrib.get("Id", "") if de_node is not None else ""

    gTimb = find_node(root, "gTimb")
    gDatGralOpe = find_node(root, "gDatGralOpe")
    gOpeCom = find_node(root, "gOpeCom")
    gEmis = find_node(root, "gEmis")
    gDatRec = find_node(root, "gDatRec")
    gCamCond = find_node(root, "gCamCond")
    gTotSub = find_node(root, "gTotSub")

    currency = find_text(gOpeCom, "cMoneOpe", "PYG")
    est = find_text(gTimb, "dEst", "001")
    pun = find_text(gTimb, "dPunExp", "001")
    num_doc = find_text(gTimb, "dNumDoc", "")

    items = []
    for idx, item_node in enumerate(find_all_nodes(root, "gCamItem"), start=1):
        afec_iva = find_text(item_node, "iAfecIVA", "")
        tasa_iva = find_text(item_node, "dTasaIVA", "0")
        tot_ope_item = find_text(item_node, "dTotOpeItem") or find_text(item_node, "dTotBruOpeItem", "0")
        bas_exe = find_text(item_node, "dBasExe", "0")

        exenta_val = tot_ope_item if (afec_iva in ("3", "2") or tasa_iva == "0" or float(bas_exe or 0) > 0) else "0"

        items.append({
            "idx": idx,
            "code": find_text(item_node, "dCodInt", str(idx)),
            "desc": find_text(item_node, "dDesProSer", "—"),
            "unit": find_text(item_node, "dDesUniMed", "UNI"),
            "qty": fmt_num(find_text(item_node, "dCantProSer", "1"), "DEC"),
            "price": fmt_num(find_text(item_node, "dPUniProSer", "0"), currency),
            "discount": fmt_num(find_text(item_node, "dDescItem", "0"), currency),
            "exenta": fmt_num(exenta_val, currency),
            "subtotal": fmt_num(tot_ope_item, currency),
        })

    ruc_rec = find_text(gDatRec, "dRucRec")
    dv_rec = find_text(gDatRec, "dDVRec")
    rec_doc = f"{ruc_rec}-{dv_rec}" if ruc_rec else find_text(gDatRec, "dNumIDRec", "—")

    tot_gral = find_text(gTotSub, "dTotGralOpe") or find_text(gTotSub, "dTotOpe")
    if not tot_gral and items:
        tot_gral = items[0]["subtotal"].replace(".", "")

    qr_url = find_text(root, "dCarQR", "") or (f"https://ekuatia.set.gov.py/consultas/qr?nVersion=150&Id={cdc}" if cdc else "")

    return {
        "cdc": cdc,
        "cdc_formatted": fmt_cdc(cdc),
        "doc_type": find_text(gTimb, "dDesTiDE", "Factura electrónica"),
        "timbrado": find_text(gTimb, "dNumTim", "—"),
        "fe_ini_t": find_text(gTimb, "dFeIniT", "—"),
        "invoice_no": f"{est}-{pun}-{num_doc}" if num_doc else "—",
        "fe_emi": fmt_date(find_text(gDatGralOpe, "dFeEmiDE")),
        "tip_tra": find_text(gOpeCom, "dDesTipTra", "—"),
        "currency": currency,
        "currency_name": find_text(gOpeCom, "dDesMoneOpe", ""),
        "cond_ope": find_text(gCamCond, "dDCondOpe", "Contado"),
        "payment_type": find_text(gCamCond, "dDesTiPag", "Efectivo"),
        "emi_name": find_text(gEmis, "dNomEmi", "—"),
        "emi_ruc": f"{find_text(gEmis, 'dRucEm')}-{find_text(gEmis, 'dDVEmi')}" if find_text(gEmis, "dRucEm") else "—",
        "emi_dir": find_text(gEmis, "dDirEmi", "—"),
        "emi_ciu": find_text(gEmis, "dDesCiuEmi", ""),
        "emi_tel": find_text(gEmis, "dTelEmi", "—"),
        "emi_email": find_text(gEmis, "dEmailE", "—"),
        "emi_act": find_text(gEmis, "dDesActEco", "—"),
        "rec_name": find_text(gDatRec, "dNomRec", "Sin Nombre"),
        "rec_doc": rec_doc,
        "rec_dir": find_text(gDatRec, "dDirRec", "—"),
        "rec_tel": find_text(gDatRec, "dTelRec", "—"),
        "rec_email": find_text(gDatRec, "dEmailRec", "—"),
        "items": items,
        "sub_exe": fmt_num(find_text(gTotSub, "dSubExe", "0"), currency),
        "sub_5": fmt_num(find_text(gTotSub, "dSub5", "0"), currency),
        "sub_10": fmt_num(find_text(gTotSub, "dSub10", "0"), currency),
        "tot_desc": fmt_num(find_text(gTotSub, "dTotDesc", "0"), currency),
        "tot_gral": fmt_num(tot_gral, currency),
        "iva_5": fmt_num(find_text(gTotSub, "dIVA5", "0"), currency),
        "iva_10": fmt_num(find_text(gTotSub, "dIVA10", "0"), currency),
        "tot_iva": fmt_num(find_text(gTotSub, "dTotIVA", "0"), currency),
        "qr_img": make_qr_base64(qr_url),
    }

def xml_bytes_to_pdf(xml_bytes, playwright_instance=None):
    data = parse_essential_sifen_xml(xml_bytes)
    kude_template_path = os.path.join(app.root_path, "templates", "kude_pdf.html")
    if os.path.exists(kude_template_path):
        rendered_html = render_template("kude_pdf.html", d=data)
    else:
        rendered_html = render_template_string(KUDE_PDF_HTML, d=data)

    safe_name = data["cdc"] if data["cdc"] else f"kude_{int(time.time())}"
    pdf_filename = f"KuDE_{safe_name}.pdf"
    pdf_path = os.path.join(OUTPUT_DIR, pdf_filename)

    if playwright_instance is not None:
        browser = playwright_instance.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(rendered_html, wait_until="networkidle")
        page.pdf(path=pdf_path, format="A4", print_background=True, margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"})
        browser.close()
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(rendered_html, wait_until="networkidle")
            page.pdf(path=pdf_path, format="A4", print_background=True, margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"})
            browser.close()

    return pdf_path, pdf_filename

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/get-install-time", methods=["GET"])
def get_install_time():
    first_run_time = get_or_create_install_time()
    return jsonify({"first_run": first_run_time.isoformat()})

@app.route("/reset-timer", methods=["POST"])
def reset_timer():
    try:
        now = datetime.now()
        with open(INSTALL_RECORD_FILE, "w") as f:
            json.dump({"first_run": now.isoformat()}, f)
        return jsonify({"status": "success", "new_run": now.isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/convert-xml", methods=["POST"])
def convert_xml_endpoint():
    if "file" not in request.files:
        return jsonify({"error": "Koi XML file select nahi ki gayi"}), 400
    f = request.files["file"]
    pdf_path, pdf_filename = xml_bytes_to_pdf(f.read())
    return send_file(pdf_path, as_attachment=True, download_name=pdf_filename, mimetype="application/pdf")

@app.route("/fetch-ekuatia", methods=["POST", "OPTIONS"])
def fetch_ekuatia():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    try:
        body = request.get_json(silent=True) or {}
        cdc = re.sub(r"\D", "", str(body.get("cdc", "")))

        if len(cdc) != 44:
            return jsonify({"error": "Kripya sahi 44-digit CDC number enter karein."}), 400

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ]
            )
            context = browser.new_context(
                accept_downloads=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()

            xml_captured = {"bytes": None}

            def handle_response(response):
                try:
                    ctype = response.headers.get("content-type", "").lower()
                    if "xml" in ctype or response.url.endswith(".xml"):
                        b = response.body()
                        if b"<rDE" in b or b"<DE" in b:
                            xml_captured["bytes"] = b
                except Exception:
                    pass

            page.on("response", handle_response)
            page.goto("https://ekuatia.set.gov.py/consultas/", wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

            try:
                inp = page.locator("input[name='cdc'], input[placeholder*='CDC'], input[type='text']").first
                inp.wait_for(state="visible", timeout=10000)
                inp.click()
                inp.fill(cdc)
            except Exception:
                pass

            captcha_clicked = False
            consultar_clicked = False
            start_time = time.time()

            while time.time() - start_time < 120:
                if xml_captured["bytes"]:
                    break

                if not captcha_clicked:
                    try:
                        rc_frame = page.frame_locator("iframe[src*='recaptcha/api2/anchor'], iframe[title*='reCAPTCHA']").first
                        checkbox = rc_frame.locator("#recaptcha-anchor")
                        if checkbox.is_visible(timeout=800):
                            checkbox.click()
                            captcha_clicked = True
                            page.wait_for_timeout(1200)
                    except Exception:
                        pass

                if not consultar_clicked:
                    try:
                        rc_frame = page.frame_locator("iframe[src*='recaptcha/api2/anchor'], iframe[title*='reCAPTCHA']").first
                        is_checked = rc_frame.locator("#recaptcha-anchor[aria-checked='true']").count() > 0
                        if is_checked:
                            consultar_btn = page.locator("button:has-text('Consultar'), input[value*='Consultar'], button[type='submit']").first
                            if consultar_btn.is_visible(timeout=800):
                                consultar_btn.click()
                                consultar_clicked = True
                                page.wait_for_timeout(1500)
                    except Exception:
                        pass

                try:
                    xml_btn = page.locator("button:has-text('Descargar XML'), a:has-text('Descargar XML'), button:has-text('XML')").first
                    if xml_btn.is_visible(timeout=500):
                        with page.expect_download(timeout=15000) as dl_info:
                            xml_btn.click()
                        dl = dl_info.value
                        temp_xml = os.path.join(OUTPUT_DIR, dl.suggested_filename or f"{cdc}.xml")
                        dl.save_as(temp_xml)
                        with open(temp_xml, "rb") as xf:
                            xml_captured["bytes"] = xf.read()
                        break
                except Exception:
                    pass

                page.wait_for_timeout(800)

            browser.close()

            if not xml_captured["bytes"]:
                return jsonify({"error": "XML download nahi ho paya (Time out ya reCAPTCHA clear nahi hua)."}), 408

            pdf_path, pdf_filename = xml_bytes_to_pdf(xml_captured["bytes"], playwright_instance=p)
            with open(pdf_path, "rb") as pf:
                pdf_b64 = base64.b64encode(pf.read()).decode("utf-8")

            return jsonify({
                "xml_text": xml_captured["bytes"].decode("utf-8", errors="replace"),
                "pdf_base64": pdf_b64,
                "pdf_filename": pdf_filename
            })

    except Exception as e:
        return jsonify({"error": f"Python Backend Error: {str(e)}"}), 500

if __name__ == "__main__":
    print("App running at: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)