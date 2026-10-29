"""Taller 4: fases 2 a 5 de ambulancias y accidentes SUMO/TraCI.

Ejecutar desde la carpeta que contiene reto.sumocfg.
La gestión de emergencias de la fase 4 todavía no está implementada.
"""

import csv
import os
import random
import sys
import time
from collections import deque
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.append(os.path.join(os.environ.get("SUMO_HOME", "/usr/share/sumo"), "tools"))

import traci
import sumolib


SEED = 42
rng = random.Random(SEED)
DURACION_SIMULACION = 10800
FIN_RETORNOS = 12600
ACCIDENTES_POR_HORA = 5
VELOCIDAD_CHOQUE = 22.0
TIEMPO_MAX_CHOQUE = 90
TIEMPO_MAX_INSERCION = 30

HOSPITALES = {
    "VCM": {"nombre": "Vicente Corral Moscoso", "tipo": "público", "lon": -78.992923, "lat": -2.911098},
    "IESS_JCA": {"nombre": "José Carrasco Arteaga", "tipo": "público", "lon": -78.970118, "lat": -2.898698},
    "MILITAR": {"nombre": "Militar HB-III Tarqui", "tipo": "público", "lon": -79.003968, "lat": -2.903146},
    "MUNI_PAT": {"nombre": "Municipal Patamarca", "tipo": "público", "lon": -78.982263, "lat": -2.866103},
    "MUNI_VALLE": {"nombre": "Municipal El Valle", "tipo": "público", "lon": -78.961959, "lat": -2.919522},
    "MONTE_SINAI": {"nombre": "Monte Sinaí", "tipo": "privado", "lon": -79.007373, "lat": -2.908606},
    "DEL_RIO": {"nombre": "Universitario del Río", "tipo": "privado", "lon": -78.960796, "lat": -2.892939},
}


def generar_agenda_accidentes():
    agenda = []
    for hora in range(3):
        inicio = max(hora * 3600, 300)
        agenda.extend(rng.sample(range(inicio, (hora + 1) * 3600), ACCIDENTES_POR_HORA))
    return sorted(agenda)


agenda_accidentes = []
indice_accidente = 0
intentos_accidente = {}
motos_pendientes = {}
accidentes_registrados = {}
pares_detectados = set()
vehiculos_por_inmovilizar = {}
contador_motos = 0
intentos_iniciados = 0
intentos_fallidos = 0
ambulancias = {}
stock_historico = []
CONTADOR_RUTAS_AMB = 0
TIEMPO_ATENCION = 120
REINTENTO_DESPACHO = 30
PROB_RECHAZO = 0.25
teleports_iniciados = 0


def reprogramar(t, motivo):
    global indice_accidente
    nuevo_tiempo = int(t + 60)
    if nuevo_tiempo >= DURACION_SIMULACION:
        print(f"[t={t:.0f}s] Sin reintento: fuera de las tres horas ({motivo}).")
        return
    agenda_accidentes.append(nuevo_tiempo)
    agenda_accidentes[indice_accidente:] = sorted(agenda_accidentes[indice_accidente:])
    print(f"[t={t:.0f}s] Reintento en t={nuevo_tiempo}s ({motivo}).")


def activar_moto_imprudente(moto_id):
    traci.vehicle.setSpeedMode(moto_id, 0)
    traci.vehicle.setLaneChangeMode(moto_id, 0)
    traci.vehicle.setSpeed(moto_id, VELOCIDAD_CHOQUE)
    traci.vehicle.setColor(moto_id, (255, 140, 0, 255))
    print(f"  Moto {moto_id} activada: speedMode=0, v={VELOCIDAD_CHOQUE:.1f} m/s")


def provocar_accidente(t):
    global contador_motos, intentos_iniciados
    buses_validos = []
    buses_ocupados = {datos["bus"] for datos in intentos_accidente.values()}
    buses_ocupados.update(datos["bus"] for datos in accidentes_registrados.values())

    for veh_id in traci.vehicle.getIDList():
        if veh_id in buses_ocupados or traci.vehicle.getTypeID(veh_id) != "bus":
            continue
        arista = traci.vehicle.getRoadID(veh_id)
        if (not arista.startswith(":") and traci.vehicle.getSpeed(veh_id) > 4
                and traci.vehicle.getLanePosition(veh_id) > 60):
            buses_validos.append(veh_id)

    if not buses_validos:
        print(f"[t={t:.0f}s] No hay buses válidos.")
        return False

    bus_id = rng.choice(buses_validos)
    arista = traci.vehicle.getRoadID(bus_id)
    carril = traci.vehicle.getLaneID(bus_id)
    indice_carril = traci.vehicle.getLaneIndex(bus_id)
    posicion_bus = traci.vehicle.getLanePosition(bus_id)
    seguidor = traci.vehicle.getFollower(bus_id, 80)
    moto_id = None

    if seguidor and seguidor[0]:
        candidato = seguidor[0]
        if (traci.vehicle.getTypeID(candidato) == "moto"
                and candidato not in intentos_accidente
                and traci.vehicle.getLaneID(candidato) == carril):
            moto_id = candidato

    print(f"\n[t={t:.0f}s] PREPARANDO ACCIDENTE | bus={bus_id} | arista={arista} "
          f"| carril={carril} | pos={posicion_bus:.2f} m")

    if moto_id is None:
        ruta_bus = list(traci.vehicle.getRoute(bus_id))
        indice_ruta = traci.vehicle.getRouteIndex(bus_id)
        ruta_restante = ruta_bus[indice_ruta:] if indice_ruta >= 0 else []
        if not ruta_restante:
            print("  Ruta del bus no disponible.")
            return False
        contador_motos += 1
        moto_id = f"moto_acc_{contador_motos}"
        traci.route.add(f"ruta_{moto_id}", ruta_restante)
        traci.vehicle.add(
            vehID=moto_id,
            routeID=f"ruta_{moto_id}",
            typeID="moto",
            depart="now",
            departLane=str(indice_carril),
            departPos=str(posicion_bus - 45),
            departSpeed="0",
        )
        motos_pendientes[moto_id] = {"bus": bus_id, "t_solicitud": t}
        print(f"  Moto solicitada: {moto_id} (45 m detrás)")
    else:
        activar_moto_imprudente(moto_id)

    intentos_accidente[moto_id] = {
        "bus": bus_id,
        "inicio": t,
        "activada": moto_id not in motos_pendientes,
    }
    intentos_iniciados += 1
    return True


def procesar_motos_pendientes(t):
    global intentos_fallidos
    actuales = set(traci.vehicle.getIDList())
    for moto_id, datos in list(motos_pendientes.items()):
        if moto_id in actuales:
            activar_moto_imprudente(moto_id)
            intentos_accidente[moto_id]["activada"] = True
            intentos_accidente[moto_id]["inicio"] = t
            del motos_pendientes[moto_id]
            print(f"[t={t:.0f}s] Moto {moto_id} insertada y activada")
        elif t - datos["t_solicitud"] >= TIEMPO_MAX_INSERCION:
            print(f"[t={t:.0f}s] Inserción fallida: {moto_id}")
            del motos_pendientes[moto_id]
            intentos_accidente.pop(moto_id, None)
            intentos_fallidos += 1
            # Si quedó pendiente en SUMO, cancelar su inserción si el backend lo permite.
            try:
                traci.vehicle.remove(moto_id)
            except traci.TraCIException:
                pass
            reprogramar(t, "moto no insertada")


def inmovilizar_accidentado(veh_id, t):
    if veh_id not in traci.vehicle.getIDList():
        return
    traci.vehicle.setSpeedMode(veh_id, 0)
    traci.vehicle.setLaneChangeMode(veh_id, 0)
    traci.vehicle.setSpeed(veh_id, 0)
    traci.vehicle.setColor(veh_id, (255, 0, 0, 255))
    vehiculos_por_inmovilizar[veh_id] = t + 1


def mantener_accidentados(t):
    actuales = set(traci.vehicle.getIDList())
    for veh_id, instante in list(vehiculos_por_inmovilizar.items()):
        if t >= instante:
            if veh_id in actuales:
                traci.vehicle.setSpeedMode(veh_id, 31)
                traci.vehicle.setSpeed(veh_id, 0)
            del vehiculos_por_inmovilizar[veh_id]


def detectar_accidentes(t):
    """Registrar una sola vez cada choque bus-moto asociado a un intento activo."""
    actuales = set(traci.vehicle.getIDList())
    for colision in traci.simulation.getCollisions():
        if {colision.colliderType, colision.victimType} != {"bus", "moto"}:
            continue
        if colision.colliderType == "bus":
            bus_id, moto_id = colision.collider, colision.victim
        else:
            bus_id, moto_id = colision.victim, colision.collider

        par = frozenset((bus_id, moto_id))
        if par in pares_detectados:
            continue
        intento = intentos_accidente.get(moto_id)
        if intento is None or not intento["activada"]:
            continue
        # La moto puede impactar otro bus: se registra el par realmente detectado.
        if bus_id not in actuales or moto_id not in actuales:
            print(f"[t={t:.0f}s] Choque observado, pero vehículo ausente: {bus_id}/{moto_id}")
            continue

        try:
            x, y = traci.vehicle.getPosition(bus_id)
            lon, lat = traci.simulation.convertGeo(x, y)
            arista = traci.vehicle.getRoadID(bus_id)
            if arista.startswith(":"):
                ruta = traci.vehicle.getRoute(bus_id)
                indice = traci.vehicle.getRouteIndex(bus_id)
                if 0 <= indice + 1 < len(ruta):
                    arista = ruta[indice + 1]
            numero = len(accidentes_registrados) + 1
            accidente_id = f"ACC_{numero:02d}"
            poi_id = f"POI_{accidente_id}"
            traci.poi.add(
                poiID=poi_id, x=x, y=y, color=(255, 255, 0, 255),
                poiType="accidente", layer=200,
            )
            traci.poi.setWidth(poi_id, 12)
        except traci.TraCIException as error:
            print(f"[t={t:.0f}s] Error registrando {bus_id}/{moto_id}: {error}")
            continue

        # Solo deduplicar tras crear exitosamente el POI y tomar las coordenadas.
        pares_detectados.add(par)
        accidentes_registrados[accidente_id] = {
            "tiempo": t, "bus": bus_id, "moto": moto_id,
            "bus_programado": intento["bus"], "arista": arista,
            "carril": colision.lane, "posicion": colision.pos,
            "x": x, "y": y, "lon": lon, "lat": lat,
            "poi": poi_id, "estado": "espera",
            "t_despacho": None, "t_llegada": None,
            "t_fin": None, "t_retorno": None,
            "hospital_origen": None, "hospital_retorno": None,
            "ambulancia": None, "eta": None,
            "reintentos": 0, "proximo_intento": t,
            "espera": None, "respuesta": None,
            "ruta_ida": "", "ruta_retorno": "",
        }
        inmovilizar_accidentado(bus_id, t)
        inmovilizar_accidentado(moto_id, t)
        intentos_accidente.pop(moto_id, None)
        motos_pendientes.pop(moto_id, None)

        print("\n" + "=" * 55)
        print(f"ACCIDENTE REAL REGISTRADO: {accidente_id}")
        print("=" * 55)
        print(f"Tiempo: {t:.0f} s | Bus: {bus_id} | Moto: {moto_id}")
        print(f"Arista: {arista} | Carril: {colision.lane} | Posición: {colision.pos:.2f} m")
        print(f"Longitud: {lon:.6f} | Latitud: {lat:.6f}")
        print(f"POI amarillo: {poi_id} | Estado: ESPERANDO AMBULANCIA")
        if intento["bus"] != bus_id:
            print(f"Aviso: la moto impactó a {bus_id}, no al bus programado {intento['bus']}")
        print("=" * 55 + "\n")


def controlar_intentos(t):
    global intentos_fallidos
    actuales = set(traci.vehicle.getIDList())
    for moto_id, intento in list(intentos_accidente.items()):
        if not intento["activada"] or t - intento["inicio"] < TIEMPO_MAX_CHOQUE:
            continue
        print(f"[t={t:.0f}s] Intento fallido: {moto_id}; sin colisión en 90 s")
        if moto_id in actuales:
            traci.vehicle.setSpeedMode(moto_id, 31)
            traci.vehicle.setLaneChangeMode(moto_id, 1621)
            traci.vehicle.setSpeed(moto_id, -1)
            traci.vehicle.setColor(moto_id, (255, 0, 255, 255))
        del intentos_accidente[moto_id]
        intentos_fallidos += 1
        reprogramar(t, "colisión no confirmada")


# ---------------------------------------------------------
# FASE 4: SELECCIÓN, DESPACHO, ATENCIÓN Y RETORNO
# ---------------------------------------------------------

def ruta_valida(origen_edge, destino_edge):
    """Consultar la ruta estimada para ambulancias sin alterar la red."""
    try:
        ruta = traci.simulation.findRoute(origen_edge, destino_edge, vType="ambulance")
        if ruta.edges and ruta.travelTime >= 0:
            return ruta
    except traci.TraCIException:
        pass
    return None


def elegir_hospital_salida(acc):
    """Entre los hospitales que aceptan, elegir el menor tiempo de viaje."""
    candidatos = []
    for h_id, h in HOSPITALES.items():
        if not h["cola"]:
            h["rechazos_sin_unidad"] += 1
            continue
        if rng.random() < h["p_sin"]:
            h["rechazos_probabilidad"] += 1
            continue
        ruta = ruta_valida(h["edge"], acc["arista"])
        if ruta is not None:
            candidatos.append((ruta.travelTime, h_id, ruta))
    return min(candidatos, key=lambda c: c[0]) if candidatos else None


def despachar_ambulancias(t):
    global CONTADOR_RUTAS_AMB
    for acc_id, acc in accidentes_registrados.items():
        if acc["estado"] != "espera" or t < acc["proximo_intento"]:
            continue
        elegido = elegir_hospital_salida(acc)
        if elegido is None:
            acc["reintentos"] += 1
            acc["proximo_intento"] = t + REINTENTO_DESPACHO
            print(f"[t={t:.0f}s] {acc_id}: sin ambulancia disponible; "
                  f"reintento #{acc['reintentos']} en 30 s")
            continue

        eta, h_id, ruta = elegido
        hospital = HOSPITALES[h_id]
        unidad = hospital["cola"].popleft()
        CONTADOR_RUTAS_AMB += 1
        route_id = f"ruta_emergencia_{CONTADOR_RUTAS_AMB}"
        try:
            traci.route.add(route_id, ruta.edges)
            traci.vehicle.add(
                vehID=unidad, routeID=route_id, typeID="ambulance",
                depart="now", departPos=str(hospital["pos"]),
            )
        except traci.TraCIException as error:
            hospital["cola"].appendleft(unidad)
            acc["reintentos"] += 1
            acc["proximo_intento"] = t + REINTENTO_DESPACHO
            print(f"[t={t:.0f}s] {acc_id}: no se pudo crear {unidad}: {error}")
            continue

        hospital["despachos"] += 1
        acc.update({
            "estado": "en_camino", "t_despacho": t, "espera": t - acc["tiempo"],
            "hospital_origen": h_id, "ambulancia": unidad, "eta": eta,
            "ruta_ida": " ".join(ruta.edges),
        })
        ambulancias[unidad] = {
            "accidente": acc_id, "estado": "en_camino", "ultima_ruta": t,
            "detenida_desde": None, "t_inicio": t, "h_origen": h_id,
            "h_retorno": None, "insertada": False,
        }
        print(f"[t={t:.0f}s] DESPACHO {acc_id}: {unidad} desde {h_id} "
              f"| ETA={eta:.1f}s | espera={acc['espera']:.0f}s "
              f"| disponibles={len(hospital['cola'])}")


def registrar_llegada(acc, unidad, t, criterio):
    acc["estado"] = "atendiendo"
    acc["t_llegada"] = t
    acc["respuesta"] = t - acc["t_despacho"]
    ambulancias[unidad]["estado"] = "atendiendo"
    if unidad in traci.vehicle.getIDList():
        traci.vehicle.setSpeedMode(unidad, 0)
        traci.vehicle.setLaneChangeMode(unidad, 0)
        traci.vehicle.setSpeed(unidad, 0)
    print(f"[t={t:.0f}s] LLEGADA {unidad} a {ambulancias[unidad]['accidente']} "
          f"({criterio}) | respuesta={acc['respuesta']:.0f}s "
          f"| total={t - acc['tiempo']:.0f}s")


def elegir_hospital_retorno(acc):
    candidatos = []
    for h_id, hospital in HOSPITALES.items():
        ruta = ruta_valida(acc["arista"], hospital["edge"])
        if ruta is not None:
            candidatos.append((ruta.travelTime, h_id))
    return min(candidatos, key=lambda r: r[0])[1] if candidatos else None


def cerrar_mision(unidad, t, motivo="llegada"):
    mision = ambulancias[unidad]
    acc = accidentes_registrados[mision["accidente"]]
    destino = mision["h_retorno"]
    if mision["estado"] == "cerrado" or destino is None:
        return
    HOSPITALES[destino]["cola"].append(unidad)
    HOSPITALES[destino]["retornos"] += 1
    HOSPITALES[mision["h_origen"]]["segundos_ocupados"] += t - mision["t_inicio"]
    mision["estado"] = "cerrado"
    acc["estado"] = "cerrado"
    acc["t_retorno"] = t
    print(f"[t={t:.0f}s] MISIÓN CERRADA {unidad} -> {destino} "
          f"({motivo}) | duración={t - mision['t_inicio']:.0f}s "
          f"| stock={len(HOSPITALES[destino]['cola'])}")


def comenzar_retorno(acc, unidad, t, activos):
    #h_id = elegir_hospital_retorno(acc)
    # EXTENSIÓN 4.7.9:
    # Retorno obligatorio al hospital de origen

    h_id = acc["hospital_origen"]
    if h_id is None:
        print(f"[t={t:.0f}s] {unidad}: no hay ruta de retorno; se reintentará")
        return
    mision = ambulancias[unidad]
    hospital = HOSPITALES[h_id]

    # Cuando la ambulancia ya abandonó la red (llegó a fin de ruta),
    # reinsertarla para que pueda iniciar su retorno.
    if unidad not in activos:
        ruta = ruta_valida(acc["arista"], hospital["edge"])
        if ruta is None:
            return
        global CONTADOR_RUTAS_AMB
        CONTADOR_RUTAS_AMB += 1
        ruta_id = f"ruta_retorno_{CONTADOR_RUTAS_AMB}"
        traci.route.add(ruta_id, ruta.edges)
        nueva_unidad = f"{unidad}_ret{CONTADOR_RUTAS_AMB}"
        traci.vehicle.add(
            vehID=nueva_unidad, routeID=ruta_id, typeID="ambulance",
            depart="now", departPos="base",
        )
        ambulancias[nueva_unidad] = ambulancias.pop(unidad)
        acc["ambulancia"] = nueva_unidad
        acc["ruta_retorno"] = " ".join(ruta.edges)
        unidad = nueva_unidad
        mision = ambulancias[unidad]
        print(f"[t={t:.0f}s] Ambulancia reinsertada para retorno: {unidad}")
    else:
        try:
            traci.vehicle.setSpeedMode(unidad, 31)
            traci.vehicle.setLaneChangeMode(unidad, 1621)
            traci.vehicle.setSpeed(unidad, -1)
            traci.vehicle.changeTarget(unidad, hospital["edge"])
            acc["ruta_retorno"] = " ".join(traci.vehicle.getRoute(unidad))
        except traci.TraCIException as error:
            print(f"[t={t:.0f}s] Retorno de {unidad} pendiente: {error}")
            return

    mision["estado"] = "retorno"
    mision["h_retorno"] = h_id
    acc["estado"] = "retorno"
    acc["hospital_retorno"] = h_id
    print(f"[t={t:.0f}s] FIN ATENCIÓN {mision['accidente']}: retorno de {unidad} "
          f"a {h_id} (origen: {mision['h_origen']})")


def actualizar_ambulancias(t, arribadas):
    activos = set(traci.vehicle.getIDList())
    for unidad, mision in list(ambulancias.items()):
        estado = mision["estado"]
        if estado == "cerrado":
            continue
        acc = accidentes_registrados[mision["accidente"]]

        if estado == "en_camino":
            if unidad in arribadas:
                registrar_llegada(acc, unidad, t, "fin de ruta")
                continue
            if unidad not in activos:
                continue  # todavía esperando inserción
            mision["insertada"] = True
            arista = traci.vehicle.getRoadID(unidad)
            pos = traci.vehicle.getLanePosition(unidad)
            velocidad = traci.vehicle.getSpeed(unidad)
            try:
                dist = traci.simulation.getDistanceRoad(
                    arista, pos, acc["arista"], max(0, acc["posicion"]), isDriving=True
                )
            except traci.TraCIException:
                dist = -1
            if 0 <= dist <= 50 or arista == acc["arista"] and velocidad < 0.1:
                registrar_llegada(acc, unidad, t, "distancia/carril")
                continue
            if velocidad < 0.1 and 0 <= dist <= 300:
                if mision["detenida_desde"] is None:
                    mision["detenida_desde"] = t
                elif t - mision["detenida_desde"] >= 30:
                    registrar_llegada(acc, unidad, t, "equipo a pie")
                    continue
            else:
                mision["detenida_desde"] = None
            if t - mision["ultima_ruta"] >= 60:
                try:
                    traci.vehicle.rerouteTraveltime(unidad)
                except traci.TraCIException as error:
                    print(f"[t={t:.0f}s] Aviso reroute {unidad}: {error}")
                mision["ultima_ruta"] = t

        elif estado == "atendiendo":
            if t - acc["t_llegada"] >= TIEMPO_ATENCION:
                for veh_id in (acc["bus"], acc["moto"]):
                    if veh_id in activos:
                        traci.vehicle.remove(veh_id)
                    vehiculos_por_inmovilizar.pop(veh_id, None)
                if acc["poi"] in traci.poi.getIDList():
                    traci.poi.remove(acc["poi"])
                acc["t_fin"] = t
                comenzar_retorno(acc, unidad, t, activos)

        elif estado == "retorno":
            if unidad in arribadas:
                cerrar_mision(unidad, t)
            elif unidad in activos:
                h = HOSPITALES[mision["h_retorno"]]
                arista = traci.vehicle.getRoadID(unidad)
                pos = traci.vehicle.getLanePosition(unidad)
                # El retorno también debe funcionar si el vehículo queda en su
                # arista de destino sin poder terminar formalmente la ruta.
                if arista == h["edge"] and pos >= h["pos"]:
                    traci.vehicle.remove(unidad)
                    cerrar_mision(unidad, t, "hospital alcanzado")


def guardar_stock(t):
    for h_id, h in HOSPITALES.items():
        stock_historico.append({"tiempo": t, "hospital": h_id, "stock": len(h["cola"])})


def escribir_csv(nombre, filas, campos):
    with open(nombre, "w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)


def exportar_estadisticas():
    """Fase 5.1: exportar registros completos de la simulación."""
    campos_acc = [
        "id", "tiempo", "bus", "moto", "bus_programado", "arista", "carril",
        "posicion", "x", "y", "lon", "lat", "poi", "estado", "t_despacho",
        "t_llegada", "t_fin", "t_retorno", "hospital_origen", "hospital_retorno",
        "ambulancia", "eta", "reintentos", "espera", "respuesta",
        "tiempo_total", "duracion_mision", "retorno_diferente",
        "ruta_ida", "ruta_retorno",
    ]
    filas_acc = []
    for acc_id, acc in accidentes_registrados.items():
        fila = {"id": acc_id, **acc}
        fila["tiempo_total"] = (
            acc["t_llegada"] - acc["tiempo"] if acc["t_llegada"] is not None else ""
        )
        fila["duracion_mision"] = (
            acc["t_retorno"] - acc["t_despacho"]
            if acc["t_retorno"] is not None and acc["t_despacho"] is not None else ""
        )
        fila["retorno_diferente"] = (
            int(acc["hospital_origen"] != acc["hospital_retorno"])
            if acc["hospital_origen"] and acc["hospital_retorno"] else ""
        )
        filas_acc.append(fila)
    escribir_csv("accidentes.csv", filas_acc, campos_acc)

    campos_hosp = [
        "hospital", "nombre", "tipo", "lon", "lat", "edge", "pos",
        "stock_inicial", "stock_final", "despachos", "retornos",
        "rechazos_sin_unidad", "rechazos_probabilidad", "rechazos_total",
        "segundos_ocupados", "utilizacion",
    ]
    filas_hosp = []
    for h_id, h in HOSPITALES.items():
        inicial = h["stock_inicial"]
        filas_hosp.append({
            "hospital": h_id, "nombre": h["nombre"], "tipo": h["tipo"],
            "lon": h["lon"], "lat": h["lat"], "edge": h["edge"], "pos": h["pos"],
            "stock_inicial": inicial, "stock_final": len(h["cola"]),
            "despachos": h["despachos"], "retornos": h["retornos"],
            "rechazos_sin_unidad": h["rechazos_sin_unidad"],
            "rechazos_probabilidad": h["rechazos_probabilidad"],
            "rechazos_total": h["rechazos_sin_unidad"] + h["rechazos_probabilidad"],
            "segundos_ocupados": h["segundos_ocupados"],
            "utilizacion": h["segundos_ocupados"] / (10800 * inicial) if inicial else "",
        })
    escribir_csv("hospitales.csv", filas_hosp, campos_hosp)
    escribir_csv("stock.csv", stock_historico, ["tiempo", "hospital", "stock"])
    print("\nFASE 5.1: archivos guardados: accidentes.csv, hospitales.csv, stock.csv")


def main():
    global agenda_accidentes, indice_accidente, teleports_iniciados
    amb_despachada = False
    amb_llegada_registrada = False
    t_despacho = 0
    eta_estimado = 0

    # Contadores de la Tabla 4.8. Los vehículos adicionales generados por
    # TraCI se contabilizan aparte del tráfico de fondo.
    insertados_fondo = {"car": 0, "bus": 0, "moto": 0}
    motos_accidente_insertadas = 0
    ambulancias_insertadas = 0
    colisiones_eventos = 0
    pares_colisionados = set()
    inicio_pared = time.perf_counter()

    print("=== RED VIAL (TABLA 4.8) ===")
    archivo_red = Path("cuenca_ciudad.net.xml")
    if not archivo_red.exists():
        try:
            cfg = ET.parse("reto.sumocfg").getroot()
            nodo = cfg.find("./input/net-file")
            if nodo is not None:
                archivo_red = Path(nodo.attrib["value"])
        except (OSError, ET.ParseError):
            pass
    if archivo_red.exists():
        red = sumolib.net.readNet(str(archivo_red), withInternal=False)
        print(f"Aristas: {len(red.getEdges())}")
        print(f"Semáforos: {len(red.getTrafficLights())}")
    else:
        print(f"No se encontró la red: {archivo_red}")

    traci.start(["sumo-gui", "-c", "reto.sumocfg", "--seed", str(SEED)])
    try:
        print("=== TAREA 2.1: MAPEO DE HOSPITALES ===")
        print(f"{'ID':<12} | {'TIPO':<8} | {'ARISTA':<20} | {'POS (m)':<8} | CALLE")
        print("-" * 75)
        for h_id, h in HOSPITALES.items():
            edge_id, pos, lane_idx = traci.simulation.convertRoad(
                h["lon"], h["lat"], isGeo=True, vClass="emergency"
            )
            h["edge"], h["pos"] = edge_id, pos
            x, y = traci.simulation.convert2D(edge_id, pos)
            color = (255, 0, 0, 255) if h["tipo"] == "público" else (0, 0, 255, 255)
            traci.poi.add(poiID=h_id, x=x, y=y, color=color, poiType="hospital", layer=100)
            calle = traci.edge.getStreetName(edge_id) or "N/A"
            print(f"{h_id:<12} | {h['tipo']:<8} | {edge_id:<20} | {pos:<8.1f} | {calle}")

        print("\n=== TAREA 2.2: STOCK INICIAL DE AMBULANCIAS ===")
        for h_id, h in HOSPITALES.items():
            stock = rng.randint(1, 3) if h["tipo"] == "público" else rng.randint(0, 1)
            h["cola"] = deque(f"{h_id}_U{i+1}" for i in range(stock))
            h["p_sin"] = 0.25
            h["stock_inicial"] = stock
            h["despachos"] = 0
            h["retornos"] = 0
            h["rechazos_sin_unidad"] = 0
            h["rechazos_probabilidad"] = 0
            h["segundos_ocupados"] = 0
            print(f"{h_id:<12}: {stock} unidades -> {list(h['cola'])}")

        agenda_accidentes = generar_agenda_accidentes()
        print("\n=== TAREA 3.1: AGENDA DE ACCIDENTES ===")
        for i, instante in enumerate(agenda_accidentes, 1):
            print(f"Evento {i:02d} | t={instante:5d}s | hora={instante // 3600 + 1}")

        print("\n=== AVANZANDO SIMULACIÓN ===")
        guardar_stock(0)
        while traci.simulation.getTime() < FIN_RETORNOS:
            traci.simulationStep()
            t = traci.simulation.getTime()
            teleports_iniciados += traci.simulation.getStartingTeleportNumber()
            arribadas = set(traci.simulation.getArrivedIDList())

            for veh_id in traci.simulation.getDepartedIDList():
                try:
                    tipo = traci.vehicle.getTypeID(veh_id)
                except traci.TraCIException:
                    continue
                if tipo == "moto" and veh_id.startswith("moto_acc_"):
                    motos_accidente_insertadas += 1
                elif tipo in insertados_fondo:
                    insertados_fondo[tipo] += 1
                elif tipo == "ambulance":
                    ambulancias_insertadas += 1

            # Todos los eventos reportados por SUMO (pueden repetirse varios
            # pasos si los vehículos accidentados permanecen solapados).
            colisiones_paso = traci.simulation.getCollisions()
            colisiones_eventos += len(colisiones_paso)
            for choque in colisiones_paso:
                pares_colisionados.add(frozenset((choque.collider, choque.victim)))

            # La detección ocurre ANTES del vencimiento de intentos.
            detectar_accidentes(t)
            mantener_accidentados(t)
            if t < DURACION_SIMULACION:
                controlar_intentos(t)

            # Fase 4: primero actualizar misiones anteriores y después asignar
            # los accidentes en espera, incluidos los recién detectados.
            actualizar_ambulancias(t, arribadas)
            despachar_ambulancias(t)
            if int(t) % 60 == 0:
                guardar_stock(t)

            if not amb_despachada and t >= 120:
                origen, destino = HOSPITALES["VCM"], HOSPITALES["IESS_JCA"]
                ruta = traci.simulation.findRoute(
                    origen["edge"], destino["edge"], vType="ambulance"
                )
                if ruta.edges:
                    traci.route.add("route_test", ruta.edges)
                    traci.vehicle.add(
                        vehID="amb_test", routeID="route_test", typeID="ambulance",
                        depart="now", departPos=str(origen["pos"]),
                    )
                    amb_despachada, t_despacho, eta_estimado = True, t, ruta.travelTime
                    print(f"[t={t:.0f}s] Ambulancia VCM -> IESS_JCA | "
                          f"{len(ruta.edges)} aristas | ETA={eta_estimado:.2f}s")

            while (t < DURACION_SIMULACION
                   and indice_accidente < len(agenda_accidentes)
                   and t >= agenda_accidentes[indice_accidente]):
                indice_accidente += 1
                print(f"\n[t={t:.0f}s] EVENTO PROGRAMADO {indice_accidente} ACTIVADO")
                if not provocar_accidente(t):
                    reprogramar(t, "sin bus o ruta válida")

            procesar_motos_pendientes(t)

            if "amb_test" in arribadas and not amb_llegada_registrada:
                amb_llegada_registrada = True
                duracion = t - t_despacho
                print(f"\n[t={t:.0f}s] AMBULANCIA DE PRUEBA LLEGÓ | "
                      f"real={duracion:.2f}s | ETA={eta_estimado:.2f}s "
                      f"| diferencia={duracion - eta_estimado:.2f}s")

        print("\n========== RESUMEN FASES 3 Y 4 ==========")
        print(f"Tiempo simulado: {traci.simulation.getTime():.0f}s")
        print(f"Eventos iniciales: {3 * ACCIDENTES_POR_HORA}")
        print(f"Intentos iniciados: {intentos_iniciados}")
        print(f"Intentos fallidos: {intentos_fallidos}")
        print(f"Accidentes reales registrados: {len(accidentes_registrados)}")
        for hora in range(3):
            n = sum(hora * 3600 <= a["tiempo"] < (hora + 1) * 3600
                    for a in accidentes_registrados.values())
            print(f"Hora {hora + 1}: {n} accidentes")
        for estado in ("espera", "en_camino", "atendiendo", "retorno", "cerrado"):
            cantidad = sum(a["estado"] == estado for a in accidentes_registrados.values())
            print(f"Accidentes en estado {estado}: {cantidad}")
        respuestas = [a["respuesta"] for a in accidentes_registrados.values()
                     if a["respuesta"] is not None]
        if respuestas:
            print(f"Respuesta media despacho→llegada: {sum(respuestas)/len(respuestas):.1f}s")
        print("\nHospital        Stock inicial/final | Despachos | Retornos | Rechazos")
        for h_id, h in HOSPITALES.items():
            print(f"{h_id:<15} {h['stock_inicial']:>2}/{len(h['cola']):<2} "
                  f"| {h['despachos']:>3} | {h['retornos']:>3} "
                  f"| {h['rechazos_sin_unidad'] + h['rechazos_probabilidad']:>3}")
        print("\n========== DATOS PARA TABLA 4.8 ==========")
        for tipo, n in insertados_fondo.items():
            print(f"Vehículos de fondo insertados ({tipo}): {n}")
        print(f"Motos de accidente insertadas por TraCI: {motos_accidente_insertadas}")
        print(f"Ambulancias insertadas (incluida prueba/reinserciones): {ambulancias_insertadas}")
        print(f"Total vehículos de fondo insertados: {sum(insertados_fondo.values())}")
        print(f"Colisiones SUMO (eventos por paso): {colisiones_eventos}")
        print(f"Pares únicos involucrados en colisiones SUMO: {len(pares_colisionados)}")
        print(f"Accidentes bus-moto registrados por TraCI: {len(accidentes_registrados)}")
        print(f"Teleports iniciados (SUMO): {teleports_iniciados}")
        exportar_estadisticas()
        print(f"Tiempo real de pared: {time.perf_counter() - inicio_pared:.2f} s")
    finally:
        traci.close()


if __name__ == "__main__":
    main()
