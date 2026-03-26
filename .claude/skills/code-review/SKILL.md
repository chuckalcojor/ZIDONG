---
name: Code Review A3
description: Revision de codigo del proyecto A3 Veterinaria con checklist de calidad
---

# Code Review A3

Realiza una revision de codigo siguiendo este checklist adaptado al proyecto A3.

## Checklist

### Correctitud
- [ ] La logica cumple con los SOPs del modulo correspondiente
- [ ] Los edge cases estan cubiertos (cliente no encontrado, API caida, etc.)
- [ ] No hay bugs obvios en el flujo conversacional

### Separacion de zonas
- [ ] El cambio esta en la zona correcta (agente vs plataforma vs conexiones)
- [ ] No se mezcla codigo de INTERNO-EQUIPO con DESARROLLO-A3
- [ ] Si toca la BD, esta documentado en 3-conexiones/

### Seguridad
- [ ] Sin secretos hardcodeados (todo via .env)
- [ ] Webhooks validan su secret header
- [ ] Inputs sanitizados antes de enviar a Supabase/OpenAI

### Calidad
- [ ] Nombrado claro y consistente (snake_case)
- [ ] Logica pura en logic.py, I/O en services/
- [ ] Sin imports no usados
- [ ] Sin codigo duplicado

## Formato de salida
Para cada issue:
1. Archivo y linea
2. Severidad (critico/medio/bajo)
3. Zona afectada (agente/plataforma/conexiones)
4. Descripcion y sugerencia de fix
