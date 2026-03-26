---
name: Refactor A3
description: Refactorizacion guiada respetando las zonas del proyecto A3
---

# Refactor A3

Refactorizar codigo manteniendo el comportamiento y respetando la separacion de zonas.

## Proceso

1. **Identificar zona** - Confirmar que el cambio pertenece a la zona correcta
2. **Revisar SOPs** - Leer los SOPs relevantes del modulo antes de tocar codigo
3. **Verificar dependencias** - Asegurarse de que no se rompen imports entre zonas
4. **Planificar** - Describir los cambios antes de hacerlos
5. **Ejecutar** - Aplicar cambios incrementales
6. **Verificar** - Confirmar que el flujo principal sigue funcionando

## Code smells a buscar en este proyecto
- Funciones de mas de 30 lineas en main.py (extraer a logic.py o helpers)
- Logica de negocio en templates HTML (mover a Python)
- Servicios con responsabilidades mixtas
- Datos hardcodeados que deberian estar en .env o Supabase
- Duplicacion entre flujo IA y flujo legacy

## Reglas
- Nunca cambiar comportamiento y refactorizar en el mismo paso
- Respetar la separacion: logica pura en logic.py, I/O en services/
- No mover codigo entre zonas sin documentar en docs/decisions/
- Actualizar el CLAUDE.md del modulo si cambia la estructura
