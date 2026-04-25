---
tags: [reunion, cliente, ia, presupuesto]
area: proyectos
fecha: 2026-02-20
participantes: [Gorka, Dr. Iñaki Zubicaray, Rosa Fernández]
---

# Reunión — Proyecto IA Gestión Pacientes — Clínica Salud Integral — 2026-02-20

## Objetivo
Explorar implantación de solución de IA para mejorar gestión de citas, triaje inicial y documentación clínica.

## Puntos tratados

- Clínica Salud Integral: clínica privada con 18 especialidades, ~120 consultas/día, 3 centros en Bilbao.
- Problema principal: recepción saturada gestionando citas, llamadas y documentación manualmente.
- Casos de uso identificados:
  1. Chatbot para citas online y consultas frecuentes (horarios, precios, preparación pruebas)
  2. Asistente IA para que médicos dicten notas clínicas y se genere documentación automáticamente
  3. Triaje inicial: cuestionario síntomas → recomendación especialidad
- Sensibilidad datos: datos de salud (LOPD + RGPD). El Dr. Zubicaray es muy claro: **todo debe ser on-premise, ningún dato a la nube**.
- Rosa Fernández (administración) pregunta por integración con su software de gestión clínica (Clinic Cloud).
- Presupuesto orientativo que maneja el cliente: 40.000-60.000€ para fase inicial.

## Decisiones tomadas

- Solución 100% on-premise obligatorio. Se propone nuestra plataforma IA local con Ollama + modelos locales.
- Se priorizará caso de uso 1 (chatbot citas) como fase 1 por ROI más claro e inmediato.
- Casos de uso 2 y 3 quedan para fases posteriores pendientes de evaluación.
- Se firmará NDA antes de compartir documentación técnica de Clinic Cloud.

## Acciones

| Acción | Responsable | Fecha límite |
|--------|-------------|--------------|
| Preparar demo chatbot citas con IA local | Gorka | 2026-03-10 |
| Enviar NDA para firma | Gorka | 2026-02-25 |
| Revisar API/exportación Clinic Cloud | Rosa Fernández | 2026-03-01 |
| Propuesta económica fase 1 | Gorka | 2026-03-15 |

## Próxima reunión

2026-03-12 — Demo chatbot + presentación propuesta fase 1
