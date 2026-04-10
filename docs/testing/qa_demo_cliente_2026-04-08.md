# QA Demo Cliente - 2026-04-08

Checklist funcional basado en feedback de reunion con cliente.

## 1) Segmentacion inicial del chat

- [ ] Inicio muestra solo dos opciones:
  - 1) Soy cliente nuevo
  - 2) Ya soy cliente de A3
- [ ] Si responde texto ambiguo, repregunta segmento.
- [ ] Cliente frecuente pasa a menu operativo (rutas, resultados, pagos, PQRS, otras).

## 2) Restriccion de informacion sensible

- [ ] Si usuario se identifica como propietario/final y pregunta precios, no entrega tarifas completas.
- [ ] Mensaje de politica profesional se muestra claro y corto.

## 3) Onboarding cliente nuevo por chat (sin formularios)

- [ ] Solicita tipo: clinica o medico independiente.
- [ ] Solicita nombre/razon social.
- [ ] Solicita documento de verificacion (RUT/Camara o tarjeta profesional).
- [ ] Solicita telefono.
- [ ] Solicita adjunto documental.
- [ ] Estado final: pendiente de aprobacion humana.

## 4) Plataforma - Aprobaciones

- [ ] `/aprobaciones` carga correctamente.
- [ ] Filtros por texto, perfil y fecha funcionan.
- [ ] Aprobar actualiza estado y promueve a cliente frecuente.
- [ ] Rechazar exige motivo.
- [ ] Historial de revisiones muestra aprobado/rechazado, revisor, fecha y motivo.

## 5) Plataforma - Afiliaciones clinica-medico

- [ ] `/afiliaciones` carga correctamente.
- [ ] Se puede agregar afiliacion.
- [ ] Se puede desvincular afiliacion.
- [ ] En modo mock, las acciones responden con confirmacion simulada.

## 6) Programacion de ruta

- [ ] Pregunta explicita: direccion habitual o nueva direccion.
- [ ] Si elige nueva direccion, solicita direccion actualizada.
- [ ] Confirma solicitud programada y mantiene tono operativo.

## 7) Terminologia

- [ ] Se usa "Orden de Servicio" (no "remision").
- [ ] Copy del bot en tono tecnico y conciso.

## 8) Canales

- [ ] Telegram operativo.
- [ ] WhatsApp webhook base responde (`GET verify`, `POST inbound`).
- [ ] LiveConnect tratado como legado (sin nuevas dependencias criticas).

## Comandos de verificacion rapida

```bash
py tools/qa_smoke_platform.py
```

## Correcciones priorizadas (siguiente pasada)

1. Validar flujo completo de onboarding en pruebas reales de Telegram (con adjuntos de documento).
2. Agregar filtros de historial por rango de fechas y estado en `/aprobaciones`.
3. Crear casos QA multimensaje para transiciones entre intenciones (ruta -> resultados -> pagos).
