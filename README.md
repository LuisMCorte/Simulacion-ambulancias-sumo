# Simulación de accidentes y respuesta de ambulancias mediante SUMO y TraCI

## Descripción del proyecto

Este proyecto implementa un entorno de simulación de tráfico vehicular
en la ciudad de Cuenca, Ecuador, utilizando Simulation of Urban MObility
(SUMO), TraCI y Python.

El objetivo es analizar la generación de accidentes entre autobuses
y motocicletas, así como evaluar la capacidad de respuesta de una
flota de ambulancias distribuida entre hospitales públicos y privados.

La simulación permite generar accidentes, detectar colisiones,
despachar ambulancias, calcular rutas de emergencia y registrar
indicadores de desempeño del sistema.

## Herramientas utilizadas

- SUMO: simulación microscópica del tráfico vehicular.
- TraCI: control dinámico de vehículos y eventos.
- Python: implementación de la lógica de simulación.
- SUMO-GUI: visualización de accidentes y ambulancias.
- Pandas: procesamiento y análisis de resultados.
- Matplotlib: generación de gráficos estadísticos.
- SUMOlib: procesamiento y representación de la red vial.
- Docker: ejecución del entorno de simulación.

## Metodología

El proyecto se desarrolló mediante cinco fases principales:

### Fase 1. Configuración del escenario

Se utiliza una red vial de Cuenca obtenida a partir de información
geográfica y adaptada para su ejecución en SUMO.

El escenario incluye:

- 1577 aristas viales.
- 97 semáforos.
- Automóviles, autobuses y motocicletas.
- Siete hospitales públicos y privados.

### Fase 2. Configuración de hospitales y ambulancias

Se implementó el posicionamiento geográfico de hospitales y
la asignación inicial de ambulancias.

Cada hospital dispone de una flota determinada aleatoriamente
mediante una semilla fija para garantizar reproducibilidad.

### Fase 3. Generación y detección de accidentes

Se programaron cinco accidentes por hora durante tres horas
de simulación.

Los accidentes se generan mediante interacciones controladas
entre autobuses y motocicletas utilizando TraCI.

Se registra:

- Tiempo de ocurrencia.
- Vehículos involucrados.
- Ubicación geográfica.
- Arista y carril.
- Estado del accidente.

### Fase 4. Despacho y gestión de ambulancias

Se implementó un sistema de atención de emergencias que contempla:

- Selección de hospitales.
- Verificación de disponibilidad de ambulancias.
- Cálculo de rutas de emergencia.
- Despacho y desplazamiento.
- Atención del accidente.
- Retorno de ambulancias.
- Actualización del inventario de unidades.

Se analizaron dos políticas de retorno:

1. Retorno al hospital más cercano.
2. Retorno al hospital de origen.

### Fase 5. Análisis estadístico - (Directorio resultados_base)

Se procesaron los datos mediante Python y Pandas para obtener
indicadores del desempeño del sistema.

Entre ellos:

- Accidentes registrados por hora.
- Tiempo de respuesta de ambulancias.
- Tiempo total de atención.
- Duración de las misiones.
- Disponibilidad de ambulancias.
- Utilización hospitalaria.
- Porcentaje de retornos a hospitales distintos del origen.

## Resultados principales

| Indicador | Resultado |
|---|---:|
| Duración de generación de accidentes | 3 horas |
| Accidentes registrados | 15 |
| Accidentes por hora | 5 |
| Vehículos de tráfico de fondo | 4760 |
| Ambulancias iniciales | 10 |
| Despachos realizados | 15 |
| Misiones finalizadas | 15 |
| Tiempo medio de respuesta | 262.73 s |
| Mediana del tiempo de respuesta | 216 s |
| Percentil 90 de respuesta | 419.60 s |
| Tiempo medio de misión | 602.53 s |
| Accidentes con espera por disponibilidad | 0 |
| Retornos a un hospital diferente | 60 % |
| Teletransportes registrados | 0 |

Los resultados corresponden al escenario con retorno al hospital
más cercano.

En el directorio resultados_base se deja ver la figuras generadas con analisis.py
apatir de los archivos.csv

## Comparación de políticas de retorno (Directorio resultados_extension)


| Indicador | Hospital más cercano | Hospital de origen |
|---|---:|---:|
| Accidentes atendidos | 15 | 15 |
| Tiempo medio de respuesta | 262.73 s | 254.13 s |
| Mediana de respuesta | 216 s | 232 s |
| Duración media de misión | 602.53 s | 709.73 s |
| Retornos a otro hospital | 60 % | 0 % |

La comparación permite analizar cómo la política de retorno
influye en la duración de las misiones y la distribución
de la flota hospitalaria.

En el directorio resultados_extension se deja ver la figuras generadas con analisis.py
apatir de los archivos.csv

## Archivos principales

- `reto_ambulancias.py`: simulación de accidentes y respuesta de ambulancias.
- `reto_extension_retorno.py`: implementación de la política de retorno al origen.
- `analisi.py`: generacion de graficas aparitr de archivo .csv.
- `reto.sumocfg`: configuración de SUMO.
- `cuenca_ciudad.net.xml`: red vial utilizada.
- `vtypes.add.xml`: definición de tipos de vehículos.
- `accidentes.csv`: registro de accidentes.
- `eventos.log`: registro de eventos.
- `collisions.xml`: información de colisiones generada por SUMO.
- `resultados_base/`: resultados del escenario base.

## Ejecución

La simulación requiere SUMO y sus herramientas de Python,
incluyendo TraCI y SUMOlib.

Ejecutar desde el directorio del proyecto:

```bash
python3 reto_ambulancias.py
```

Para ejecutar el escenario con retorno al hospital de origen:

```bash
python3 reto_extension_retorno.py
```

La ejecución debe realizarse en un entorno con las dependencias
necesarias y los archivos de configuración del escenario.

## Aplicaciones

Este proyecto permite estudiar:

- Sistemas inteligentes de transporte (ITS).
- Gestión de emergencias médicas.
- Movilidad urbana.
- Simulación de tráfico.
- Optimización de recursos de emergencia.
- Evaluación de políticas de despacho y retorno de ambulancias.

## Autor

**Luis Miguel Corte**

Proyecto académico de Ingeniería en Telecomunicaciones.

Cuenca, Ecuador.
