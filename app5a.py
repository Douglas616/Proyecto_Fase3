from flask import Flask, request, Response
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime

app = Flask(__name__)
DB_PATH = "C:/Users/iront/OneDrive/Documentos/Python/Proyecto_Fase3/mensajes.db"

# Analisis de sentimiento
def clasificarr_sentimientos(texto, positivos, negativos):
    texto = texto.lower()
    puntos = {"positivo": 0, "negativo": 0}

    for palabra in positivos:
        if palabra in texto:
            puntos["positivo"] += 1
    for palabra in negativos:
        if palabra in texto:
            puntos["negativo"] += 1

    if puntos["positivo"] > puntos["negativo"]:
        return "positivo"
    elif puntos["negativo"] > puntos["positivo"]:
        return "negativo"
    else:
        return "neutro"

# Metodo POST /analizar 
@app.route('/analizar', methods=['POST'])
def analizar():
    try:
        if 'archivo' not in request.files:
            return "No se ha enviado ningún archivo XML.", 400

        archivo = request.files['archivo']
        if archivo.filename == '':
            return "Nombre de archivo vacío.", 400

        tree = ET.parse(archivo)
        root = tree.getroot()

        positivos = [p.text.lower() for p in root.findall('.//sentimientos_positivos/palabra')]
        negativos = [n.text.lower() for n in root.findall('.//sentimientos_negativos/palabra')]

        empresas = {}
        for emp in root.findall('.//empresa'):
            nombre = emp.find('nombre').text
            servicios = {}
            for s in emp.findall('servicio'):
                servicio_nombre = s.attrib.get('nombre', 'desconocido')
                alias = [a.text.lower() for a in s.findall('alias')]
                servicios[servicio_nombre] = alias
            empresas[nombre] = servicios

        mensajes = root.findall('.//mensaje')
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()

        for mensaje_elem in mensajes:
            texto_completo = mensaje_elem.text.strip()
            try:
                partes = texto_completo.split("Usuario:")
                datos = partes[0].strip().replace("Lugar y fecha:", "").strip()
                usuario_red = partes[1].strip().split("Red social:")
                usuario = usuario_red[0].strip()
                red_social = usuario_red[1].split()[0].strip()
                mensaje = "Red social:".join(usuario_red[1:]).strip()

                fecha_raw = datos.split(",")[-1].strip()
                fecha = datetime.strptime(fecha_raw, "%d/%m/%Y %H:%M")
            except Exception:
                continue  

            empresa_detectada = "desconocida"
            servicio_detectado = "desconocido"
            for emp, servicios in empresas.items():
                if emp.lower() in mensaje.lower():
                    empresa_detectada = emp
                    for s, alias in servicios.items():
                        if any(a in mensaje.lower() for a in alias):
                            servicio_detectado = s
                            break
                    break

            sentimiento = clasificarr_sentimientos(mensaje, positivos, negativos)

            cursor.execute("""
                INSERT INTO mensajes (fecha, usuario, red_social, empresa, servicio, mensaje, sentimiento)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                fecha.strftime("%Y-%m-%d %H:%M:%S"),
                usuario,
                red_social,
                empresa_detectada,
                servicio_detectado,
                mensaje,
                sentimiento
            ))

        conn.commit()
        conn.close()
        return "Archivo XML procesado correctamente y mensajes guardados."

    except ET.ParseError as e:
        return f"Error al parsear el XML: {str(e)}", 400
    except Exception as e:
        return f"Error general: {str(e)}", 500


# Metoddo GET /respuesta 
@app.route('/respuesta', methods=['GET'])
def generar_respuesta():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT fecha FROM mensajes ORDER BY fecha ASC LIMIT 1")
        fecha_row = cursor.fetchone()
        fecha_analisis = fecha_row[0][:10] if fecha_row and fecha_row[0] else "sin_fecha"

        cursor.execute("SELECT COUNT(*), sentimiento FROM mensajes GROUP BY sentimiento")
        conteos = {row[1]: row[0] for row in cursor.fetchall()}
        total = sum(conteos.values())
        positivos = conteos.get("positivo", 0)
        negativos = conteos.get("negativo", 0)
        neutros = conteos.get("neutro", 0)

        lista_respuestas = ET.Element("lista_respuestas")
        respuesta = ET.SubElement(lista_respuestas, "respuesta")
        ET.SubElement(respuesta, "fecha").text = fecha_analisis

        mensajes = ET.SubElement(respuesta, "mensajes")
        ET.SubElement(mensajes, "total").text = str(total)
        ET.SubElement(mensajes, "positivos").text = str(positivos)
        ET.SubElement(mensajes, "negativos").text = str(negativos)
        ET.SubElement(mensajes, "neutros").text = str(neutros)

        analisis = ET.SubElement(respuesta, "analisis")
        cursor.execute("SELECT DISTINCT empresa FROM mensajes")
        empresas = cursor.fetchall()

        for (empresa,) in empresas:
            empresa = empresa if empresa else "desconocida"
            empresa_elem = ET.SubElement(analisis, "empresa", nombre=empresa)

            cursor.execute("SELECT COUNT(*), sentimiento FROM mensajes WHERE empresa = ? GROUP BY sentimiento", (empresa,))
            conteos = {row[1]: row[0] for row in cursor.fetchall()}
            total_e = sum(conteos.values())
            pos = conteos.get("positivo", 0)
            neg = conteos.get("negativo", 0)
            neu = conteos.get("neutro", 0)

            empresa_mensajes = ET.SubElement(empresa_elem, "mensajes")
            ET.SubElement(empresa_mensajes, "total").text = str(total_e)
            ET.SubElement(empresa_mensajes, "positivos").text = str(pos)
            ET.SubElement(empresa_mensajes, "negativos").text = str(neg)
            ET.SubElement(empresa_mensajes, "neutros").text = str(neu)

            servicios_elem = ET.SubElement(empresa_elem, "servicios")
            cursor.execute("SELECT DISTINCT servicio FROM mensajes WHERE empresa = ?", (empresa,))
            servicios = cursor.fetchall()

            for (servicio,) in servicios:
                servicio = servicio if servicio else "desconocido"
                servicio_elem = ET.SubElement(servicios_elem, "servicio", nombre=servicio)

                cursor.execute("""
                    SELECT COUNT(*), sentimiento FROM mensajes
                    WHERE empresa = ? AND servicio = ? GROUP BY sentimiento
                """, (empresa, servicio))
                conteos = {row[1]: row[0] for row in cursor.fetchall()}
                total_s = sum(conteos.values())
                pos = conteos.get("positivo", 0)
                neg = conteos.get("negativo", 0)
                neu = conteos.get("neutro", 0)

                mensajes_servicio = ET.SubElement(servicio_elem, "mensajes")
                ET.SubElement(mensajes_servicio, "total").text = str(total_s)
                ET.SubElement(mensajes_servicio, "positivos").text = str(pos)
                ET.SubElement(mensajes_servicio, "negativos").text = str(neg)
                ET.SubElement(mensajes_servicio, "neutros").text = str(neu)

        conn.close()
        xml_str = ET.tostring(lista_respuestas, encoding="utf-8", xml_declaration=True)
        return Response(xml_str, mimetype='application/xml')

    except Exception as e:
        return f"Error al generar el XML de salida: {str(e)}", 500



if __name__ == '__main__':
    app.run(debug=True)
