# `integrals`: calculadora de integrales

Microservicio que calcula integrales a partir de texto LaTeX. Se usa por REST o desde el chat con `/integralcalc <latex>`.
El diseño, los contratos y las decisiones están en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

## Ejecutar

Este repositorio contiene solo `integrals` y su infraestructura (`rabbitmq` e `integrals-mongodb`).
El chat base (`users`, `channels`, `messages`) se levanta por separado y crea la red Docker `microsvcs`,
a la que se une este stack. Ver la sección *Requisitos del chat base*.

1. Levantar el chat base primero (crea la red `microsvcs`), desde su carpeta:

   ```bash
   docker compose up --build -d
   ```

2. Levantar `integrals` desde la raíz de este repositorio:

   ```bash
   docker compose up --build -d
   ```

Para detener, `docker compose down` en cada carpeta (primero este stack, luego el base, que es dueño de la red).

| Servicio | URL |
| --- | --- |
| `integrals` (API y `/docs`) | http://localhost:8004 |
| RabbitMQ (gestión, usuario `guest`/`guest`) | http://localhost:15672 |

### Requisitos del chat base

- Sus servicios deben estar en la red `microsvcs` con los nombres `users` y `messages`.
- `messages` necesita `RABBITMQ_URL: amqp://guest:guest@rabbitmq:5672/`. Sin esto no publica
  `chat.message.created` y el comando `/integralcalc` no llega a `integrals`.
- `rabbitmq` vive en este stack. Si `messages` publica antes de que esté arriba, el evento se pierde.

## Probar por REST

```bash
curl -X POST localhost:8004/api/v1/integrals \
  -H 'Content-Type: application/json' \
  -d '{"latex": "\\int_0^1 x^2 \\, dx"}'
```

Una integral que no se puede resolver responde `201` con `"status": "failed"` y el detalle en `error.code`
(`LATEX_INVALID`, `NOT_AN_INTEGRAL`, `UNSOLVABLE`, `TIMEOUT`). Solo la validación de forma responde `422`.

## Probar desde el chat

```bash
USER=$(curl -s -X POST localhost:8001/api/v1/users -H 'Content-Type: application/json' \
  -d '{"display_name": "ana"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
CH=$(curl -s -X POST localhost:8002/api/v1/channels -H 'Content-Type: application/json' \
  -d '{"name": "general"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')

curl -s -X POST localhost:8003/api/v1/channels/$CH/messages -H 'Content-Type: application/json' \
  -d "{\"author_id\": \"$USER\", \"content\": \"/integralcalc \\\\int_0^1 x^2 \\\\, dx\"}"

sleep 2
curl -s localhost:8003/api/v1/channels/$CH/messages
```

El bot `integralbot` responde en el canal. Se acepta `/integralcalc` y el alias `/integral`.

## Eventos

| Routing key (exchange `integrals`, tipo `topic`) | Cuándo |
| --- | --- |
| `integral.<id>.calculated` | Cálculo exitoso |
| `integral.<id>.failed` | Cálculo fallido |

Consume `chat.message.created` del exchange `chat` (publicado por `messages`).

## Pruebas

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

Las pruebas cubren el cálculo, la API, el adaptador de chat y el contrato (rutas, campos y eventos).
No cubren la conexión real con RabbitMQ, MongoDB ni los otros servicios.

## Trazabilidad

Los logs salen en JSON por stdout con `correlation_id`. En REST se usa el header `X-Correlation-ID`
(se genera si falta). En el flujo de chat, el ID del mensaje original es el `correlation_id`.

```bash
docker compose logs integrals | grep <correlation_id>
```

## Limitaciones conocidas

- Si RabbitMQ no está disponible cuando se escribe el comando, `messages` pierde el evento sin avisar (su `publish` ignora el error). Es una limitación del servicio existente.
- El cálculo y la respuesta en el chat no son una sola transacción. Si la respuesta falla, el resultado sigue disponible por REST.
- Si se borra la base de `integrals`, se crea un bot nuevo y el anterior queda huérfano en `users`.
- SymPy no resuelve todas las integrales. En esos casos el resultado es `failed` con `UNSOLVABLE`.
