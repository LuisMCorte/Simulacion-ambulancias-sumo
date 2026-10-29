import os
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

# En las imágenes Docker del curso, sumolib está fuera del sys.path normal.
_sumo_tools = os.path.join(os.environ.get("SUMO_HOME", "/usr/share/sumo"), "tools")
if _sumo_tools not in sys.path:
    sys.path.insert(0, _sumo_tools)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


RAIZ = Path(__file__).resolve().parent
SALIDA = RAIZ / "figuras"
SALIDA.mkdir(exist_ok=True)


def leer_datos():
    accidentes = pd.read_csv(RAIZ / "accidentes.csv", encoding="utf-8-sig")
    hospitales = pd.read_csv(RAIZ / "hospitales.csv", encoding="utf-8-sig")
    stock = pd.read_csv(RAIZ / "stock.csv", encoding="utf-8-sig")
    for campo in ["tiempo", "espera", "respuesta", "tiempo_total", "duracion_mision"]:
        accidentes[campo] = pd.to_numeric(accidentes[campo], errors="coerce")
    for campo in ["stock_inicial", "stock_final", "despachos", "retornos", "utilizacion"]:
        hospitales[campo] = pd.to_numeric(hospitales[campo], errors="coerce")
    return accidentes, hospitales, stock


def resumen(accidentes, hospitales):
    print("\n========== INDICADORES FASE 5 ==========")
    print(f"Accidentes registrados: {len(accidentes)}")
    for hora in range(3):
        n = ((accidentes.tiempo >= hora * 3600)
             & (accidentes.tiempo < (hora + 1) * 3600)).sum()
        print(f"Hora {hora + 1}: {n} accidentes")
    for campo, titulo in [("respuesta", "Respuesta (despacho→llegada)"),
                          ("tiempo_total", "Tiempo total (accidente→llegada)"),
                          ("duracion_mision", "Duración de misión")]:
        serie = accidentes[campo].dropna()
        if serie.empty:
            print(f"{titulo}: sin datos")
            continue
        print(f"{titulo}: mediana={serie.median():.2f}s | media={serie.mean():.2f}s "
              f"| p90={serie.quantile(.90):.2f}s | mín={serie.min():.2f}s "
              f"| máx={serie.max():.2f}s")
    espera = accidentes.espera.dropna()
    print(f"Accidentes con espera > 0: {(espera > 0).sum()} | "
          f"espera máxima: {espera.max() if not espera.empty else float('nan'):.1f}s")
    retorno = pd.to_numeric(accidentes.retorno_diferente, errors="coerce").dropna()
    print(f"Retornos a hospital distinto: {100 * retorno.mean():.1f}% "
          if not retorno.empty else "Retornos distintos: no disponibles")
    print("\nHospitales públicos:")
    for _, h in hospitales[hospitales.tipo == "público"].iterrows():
        utilizacion = f"{100 * h.utilizacion:.1f}%" if pd.notna(h.utilizacion) else "N/A"
        print(f"  {h.hospital:<12} despachos={h.despachos:>2.0f} "
              f"retornos={h.retornos:>2.0f} utilización={utilizacion}")
    inicial = hospitales.stock_inicial.sum()
    final = hospitales.stock_final.sum()
    despachos = hospitales.despachos.sum()
    retornos = hospitales.retornos.sum()
    print(f"Conservación de flota: {inicial:.0f} inicial, {final:.0f} final")
    print(f"Misiones: {despachos:.0f} despachos, {retornos:.0f} retornos")
    if inicial != final or despachos != retornos:
        print("ADVERTENCIA: stock o misiones no cuadran; revisar estados pendientes.")


def figura_respuestas(accidentes):
    datos = accidentes.dropna(subset=["respuesta"]).sort_values("tiempo")
    if datos.empty:
        return
    fig, ax = plt.subplots(figsize=(11, 5.2))
    x = np.arange(1, len(datos) + 1)
    ax.bar(x, datos.respuesta, color="#2374AB", width=.7)
    mediana, p90 = datos.respuesta.median(), datos.respuesta.quantile(.9)
    ax.axhline(mediana, color="#E67E22", linestyle="--", linewidth=2,
               label=f"Mediana = {mediana:.1f} s")
    ax.axhline(p90, color="#C0392B", linestyle=":", linewidth=2,
               label=f"p90 = {p90:.1f} s")
    ax.set(xlabel="Accidente (orden cronológico)", ylabel="Respuesta (s)",
           title="Tiempo de respuesta por accidente")
    ax.set_xticks(x, datos.id)
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(SALIDA / "RA_fig_1_respuestas.png", dpi=220)
    plt.close(fig)


def figura_hospitales(hospitales):
    h = hospitales
    x = np.arange(len(h))
    w = .25
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.bar(x - w, h.stock_inicial, w, label="Stock inicial", color="#95A5A6")
    ax.bar(x, h.despachos, w, label="Despachos", color="#2E86C1")
    ax.bar(x + w, h.retornos, w, label="Retornos", color="#27AE60")
    ax.set(xticks=x, xticklabels=h.hospital, ylabel="Número de unidades / eventos",
           title="Stock inicial, despachos y retornos por hospital")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(SALIDA / "RA_fig_2_hospitales.png", dpi=220)
    plt.close(fig)


def figura_stock(stock, hospitales):
    ids = hospitales.hospital.tolist()
    fig, axes = plt.subplots(len(ids), 1, figsize=(11, 13), sharex=True)
    for ax, h_id in zip(axes, ids):
        datos = stock[stock.hospital == h_id].sort_values("tiempo")
        ax.step(datos.tiempo / 3600, datos.stock, where="post", color="#1F618D")
        ax.set_ylabel(h_id, rotation=0, ha="right", va="center")
        ax.set_ylim(bottom=-.15)
        ax.grid(alpha=.25)
    axes[-1].set_xlabel("Tiempo simulado (horas)")
    fig.suptitle("Disponibilidad de ambulancias por hospital cada 60 s")
    fig.tight_layout(rect=(0, 0, 1, .98))
    fig.savefig(SALIDA / "RA_fig_3_stock.png", dpi=220)
    plt.close(fig)


def encontrar_red():
    directa = RAIZ / "cuenca_ciudad.net.xml"
    if directa.exists():
        return directa
    cfg = RAIZ / "reto.sumocfg"
    if cfg.exists():
        raiz = ET.parse(cfg).getroot()
        nodo = raiz.find("./input/net-file")
        if nodo is not None:
            candidata = RAIZ / nodo.attrib["value"]
            if candidata.exists():
                return candidata
    return None


def figura_mapa(accidentes, hospitales):
    try:
        import sumolib
    except ImportError as error:
        print(f"No se pudo importar sumolib: {error}")
        print(f"Ruta de herramientas SUMO buscada: {_sumo_tools}")
        print("Comprueba que exista el directorio /usr/share/sumo/tools/sumolib")
        return
    archivo_red = encontrar_red()
    if archivo_red is None:
        print("No se encontró cuenca_ciudad.net.xml: omitiendo figura 4")
        return
    red = sumolib.net.readNet(str(archivo_red), withInternal=False)
    fig, ax = plt.subplots(figsize=(11, 10))

    # Usar coordenadas métricas SUMO X/Y. No requiere pyproj.
    def dibujar_arista(edge_id, color, ancho, alpha, zorder):
        try:
            edge = red.getEdge(edge_id)
            forma = edge.getShape()
            ax.plot([p[0] for p in forma], [p[1] for p in forma],
                    color=color, linewidth=ancho, alpha=alpha, zorder=zorder)
        except (KeyError, ValueError):
            pass

    for edge in red.getEdges():
        dibujar_arista(edge.getID(), "#B9C1C8", .5, .5, 1)

    # Rutas de ida azul y retorno verde, acumuladas para todos los accidentes.
    for _, a in accidentes.iterrows():
        for campo, color in [("ruta_ida", "#2874A6"), ("ruta_retorno", "#239B56")]:
            if isinstance(a[campo], str):
                for edge_id in a[campo].split():
                    dibujar_arista(edge_id, color, 1.2, .25, 2)

    # Hospitales: su posición vial está en edge/pos del CSV.
    # Convertir esa posición a X/Y interpolando la geometría del carril.
    puntos_hospital = []
    for _, h in hospitales.iterrows():
        try:
            carril = red.getEdge(h.edge).getLane(0)
            forma = carril.getShape()
            pos_geometrica = float(h.pos) * (
                sum(((forma[i+1][0] - forma[i][0]) ** 2
                     + (forma[i+1][1] - forma[i][1]) ** 2) ** .5
                    for i in range(len(forma) - 1)) / carril.getLength()
            )
            hx, hy = sumolib.geomhelper.positionAtShapeOffset(forma, pos_geometrica)
            puntos_hospital.append((h.hospital, h.tipo, hx, hy))
        except (KeyError, ValueError, ZeroDivisionError):
            print(f"Advertencia: hospital {h.hospital} sin posición válida en la red")

    publicos = [p for p in puntos_hospital if p[1] == "público"]
    privados = [p for p in puntos_hospital if p[1] != "público"]
    ax.scatter([p[2] for p in publicos], [p[3] for p in publicos],
               marker="s", c="#C0392B", s=75,
               edgecolors="white", linewidths=.7, label="Hospital público", zorder=5)
    ax.scatter([p[2] for p in privados], [p[3] for p in privados],
               marker="s", c="#7D3C98", s=75,
               edgecolors="white", linewidths=.7, label="Hospital privado", zorder=5)
    ax.scatter(accidentes.x, accidentes.y, marker="*", c="#F1C40F", s=120,
               edgecolors="#7D6608", linewidths=.5, label="Accidente", zorder=6)
    for h_id, _, hx, hy in puntos_hospital:
        ax.annotate(h_id, (hx, hy), xytext=(4, 4),
                    textcoords="offset points", fontsize=7)
    ax.plot([], [], color="#2874A6", label="Ruta de ida")
    ax.plot([], [], color="#239B56", label="Ruta de retorno")
    ax.set(xlabel="Coordenada X de SUMO (m)", ylabel="Coordenada Y de SUMO (m)",
           title="Cuenca: hospitales, accidentes y recorridos de ambulancias")
    ax.set_aspect("equal", adjustable="datalim")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(SALIDA / "RA_fig_4_mapa.png", dpi=240)
    plt.close(fig)


def main():
    accidentes, hospitales, stock = leer_datos()
    resumen(accidentes, hospitales)
    figura_respuestas(accidentes)
    figura_hospitales(hospitales)
    figura_stock(stock, hospitales)
    figura_mapa(accidentes, hospitales)
    print(f"\nGráficos generados en: {SALIDA}")


if __name__ == "__main__":
    main()
