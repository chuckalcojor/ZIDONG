# Modulo: Plataforma / Dashboard

## Responsabilidad
Panel operativo web para el equipo interno de A3. Muestra metricas, clientes, solicitudes, muestras, analisis y estado de conversaciones.

## Estado actual
El dashboard se sirve actualmente desde Flask (templates HTML en `1-agente-conversacional/app/templates/`). Esta es una solucion temporal. El plan es migrar a un frontend separado en Next.js + React + Tailwind.

## Codigo actual (temporal, dentro del agente)
- `1-agente-conversacional/app/templates/dashboard.html` - Vista principal
- `1-agente-conversacional/app/templates/login.html` - Login
- `1-agente-conversacional/app/static/app.css` - Estilos
- Rutas en `main.py`: `/dashboard`, `/clientes`, `/muestras`, `/analisis`, `/flujo`, `/api/dashboard/overview`

## SOPs de este modulo
- `architecture/sops/05_dashboard_v1.md` - Dashboard V1
- `architecture/sops/08_dashboard_ops_center.md` - Centro de operaciones
- `architecture/sops/09_integration_payloads_dashboard.md` - Payloads de integracion

## Vistas del dashboard
| Vista | Ruta | Descripcion |
|-------|------|-------------|
| Dashboard | `/dashboard` | Metricas generales, funnel, top couriers/zones |
| Clientes | `/clientes` | Lista de clinicas con mensajero, solicitudes, muestras |
| Motorizados | `/motorizados` | Cobertura por localidad y mapa operativo |
| Muestras | `/muestras` | Estado de muestras de laboratorio |
| Analisis | `/analisis` | Catalogo de tests y analisis activos |
| Flujo | `/flujo` | Etapas conversacionales por sesion y transiciones |

## Futuro (Next.js)
Cuando se migre el frontend:
- El codigo ira en esta carpeta (`2-plataforma/`)
- Se conectara a Supabase directamente (no via Flask)
- Auth via Supabase Auth (nextjs-supabase-auth)
- UI: React + Tailwind + componentes reutilizables

## Reglas
- Cambios de UI se documentan aqui aunque el codigo viva en el agente
- Revisar SOPs antes de modificar vistas
- No agregar logica de negocio en templates
- Mantener estilos en `app.css`, no inline
