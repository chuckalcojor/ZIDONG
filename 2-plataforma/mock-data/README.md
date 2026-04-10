# Mock Data de Plataforma (SOLO DEMO)

Esta carpeta contiene datos falsos para visualizar y probar la plataforma sin depender de Supabase.

## Importante

- Estos datos NO representan operacion real.
- Estos datos NO deben usarse en produccion.
- Toda la UI del dashboard en modo `mock` lee desde `dashboard_context.json`.

## Activacion

En `DESARROLLO-A3/1-agente-conversacional/.env`:

```env
DASHBOARD_DATA_MODE=mock
```

Para volver a datos reales:

```env
DASHBOARD_DATA_MODE=real
```

## Reemplazo futuro

Cuando migremos a data real definitiva:

1. Cambiar `DASHBOARD_DATA_MODE=real`.
2. Verificar vistas.
3. Borrar esta carpeta `2-plataforma/mock-data/` sin afectar el resto del codigo.
