# Estudio Norte Reservas

Proyecto de muestra con datos ficticios. No corresponde a un cliente real. Preparado como material de portfolio con asistencia de IA; no acredita experiencia con clientes ni un sistema en producción.

## Qué se puede probar

- Selección de servicio, fecha y franjas de 30 minutos.
- Días laborables, 09:00 a 16:30, zona Europe/Madrid, hasta 90 días.
- Rechazo de horas pasadas y reservas duplicadas en el mismo almacenamiento.
- Agenda, cancelación y liberación de franjas.
- En modo SQLite, comprobación de conflictos y escritura en una transacción.

Interfaz responsive en español, etiquetas accesibles, foco visible y mensajes de estado. Sin frameworks ni dependencias de ejecución externas.

## Probar la versión estática

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

Abre http://127.0.0.1:8000. También funciona en alojamiento estático como GitHub Pages. En este modo se usa localStorage: cada navegador tiene su copia, los datos no se comparten y borrar datos del navegador los elimina. No introduzcas datos reales. No hay autenticación ni correos ni pagos.

## Probar el servidor local con SQLite

Python 3.10 o superior, sin paquetes adicionales:

```sh
python3 server.py --port 8000
```

Abre http://127.0.0.1:8000. El encabezado mostrará "Modo servidor local". Los datos se guardan en `demo.sqlite3` (excluido del repositorio). Para empezar de cero, detén el servidor y borra esa base de datos. `DEMO_DB` permite elegir otra ruta. No subas una base con datos.

El servidor escucha solo en 127.0.0.1. No lo expongas a Internet: es una demostración local sin autenticación. En SQLite los datos sí se comparten entre navegadores que usen ese mismo servidor local; en GitHub Pages no.

## Pruebas

```sh
python3 -m unittest -v
```

Pruebas de API (8 casos generales y una prueba adicional de concurrencia para reservas): listado, creación/persistencia/actualización, validación, registros inexistentes, rechazo de origen ajeno, no servir archivos privados y conflicto de horario/cancelación/reutilización. También se ejercitó la interfaz en Chromium, con recarga y vista móvil, tanto en modo estático como con SQLite.

## Estructura

- `index.html`: interfaz y formularios.
- `styles.css`: diseño responsive sin recursos remotos.
- `app.js`: interacción, validación y modo local/API.
- `server.py`: API JSON y SQLite, solo para demostración local.
- `test_server.py`: pruebas de API sin dependencias.

## Decisiones y límites

La demo pública es interactiva, no un servicio contratado. No se envían reservas, leads, mensajes ni facturas. El panel visible no es un área privada. Los nombres de negocios y contactos son ficticios y los correos usan example.com.

Antes de uso real hacen falta, entre otros: autenticación y roles, revisión de seguridad, HTTPS y despliegue con servidor adecuado, control de abuso, permisos y consentimiento, política de protección/retención de datos, copias de seguridad y recuperación, notificaciones y pruebas con usuarios. No se promete disponibilidad, cumplimiento normativo ni aceptación por ninguna plataforma.
