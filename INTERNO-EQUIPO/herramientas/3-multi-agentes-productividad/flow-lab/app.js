const STORAGE_KEY = "a3-flow-lab-v4";

const sampleData = {
  stages: [
    {
      id: "fase_0_bienvenida",
      title: "Bienvenida",
      x: 70,
      y: 80,
      goal: "Iniciar conversacion natural y abrir opciones de ayuda.",
      botReply: "Hola! Bienvenido a A3 laboratorio clinico veterinario. En que podemos ayudarte hoy?",
      userReply: "Saludo, consulta general o solicitud operativa.",
      notes: "Si solo escribe 'hola', responder y pasar a clasificacion de intencion.",
    },
    {
      id: "fase_1_clasificacion",
      title: "Clasificacion",
      x: 390,
      y: 80,
      goal: "Clasificar si la intencion es informativa, operativa o alta_cliente.",
      botReply:
        "Perfecto, te ayudo con eso. Indicanos si necesitas informacion, programar un retiro, resultados, contabilidad o registro nuevo.",
      userReply:
        "Puede pedir un analisis especifico, precio, tiempos, retiro de muestra, resultados, contabilidad o registrarse.",
      notes:
        "Cliente registrado tambien puede hacer consultas informativas sin friccion.",
    },
    {
      id: "fase_gate_identificacion",
      title: "Gate de identificacion",
      x: 710,
      y: 80,
      goal: "Para intenciones operativas, verificar si el cliente esta identificado/registrado.",
      botReply:
        "Para continuar con esta gestion, comparteme tu NIF o el nombre fiscal de la veterinaria para ubicar el registro.",
      userReply: "Entrega NIF o nombre fiscal, o confirma que aun no esta registrado.",
      notes:
        "Regla: estricto para operacion/programacion. Si no esta identificado, no avanzar a ejecucion.",
    },
    {
      id: "fase_info_consulta",
      title: "Consulta informativa",
      x: 1030,
      y: 80,
      goal: "Resolver dudas sin exigir registro previo.",
      botReply:
        "Te cuento los analisis disponibles, valores o tiempos, y si luego deseas programar retiro te acompano con ese proceso.",
      userReply:
        "Pregunta por tipo de analisis, precio, alcance, tiempos u otras dudas generales.",
      notes:
        "No bloquear por registro en consultas informativas.",
    },
    {
      id: "fase_contabilidad_pendiente",
      title: "Contabilidad (definicion pendiente)",
      x: 1030,
      y: 560,
      goal: "Registrar solicitud y mantener handoff controlado hasta definir alcance con cliente.",
      botReply:
        "Perfecto, te ayudo con contabilidad. Te comunicamos con el area correspondiente para darte una respuesta precisa.",
      userReply: "Consulta de factura, cartera, pago o documento contable.",
      notes:
        "Pendiente de definir: que consultas se responden automatico y que datos minimos pedir antes de escalar.",
    },
    {
      id: "fase_resultados_integracion_futura",
      title: "Resultados (integracion futura)",
      x: 1350,
      y: 560,
      goal: "Consultar estado con identificador y preparar integracion con plataforma de resultados.",
      botReply:
        "Perfecto, comparteme numero de muestra, orden o nombre de mascota para consultar resultados.",
      userReply: "Entrega referencia o pide estado del resultado.",
      notes:
        "Pendiente de siguiente fase: integrar API/plataforma para entregar estado y acceso a resultado especifico.",
    },
    {
      id: "fase_registro_nuevo",
      title: "Registro nuevo cliente",
      x: 390,
      y: 330,
      goal: "Guiar alta por formulario oficial para crear registro base.",
      botReply:
        "Perfecto, te ayudo con el registro como cliente nuevo. Para completar el alta, por favor diligencia este formulario: https://docs.google.com/forms/d/e/1FAIpQLScwimzCqx01C_6yMEn8caTgNWgXZ2rEYbwsFnJKM4e6ckLzLg/viewform",
      userReply: "Ok, ya lo lleno / listo / tengo una duda puntual.",
      notes:
        "Usar wording: registro manual y asi quedas registrado en nuestra base de datos. No mencionar Google Sheet.",
    },
    {
      id: "fase_2_recogida_datos_operativa",
      title: "Recogida de datos operativa",
      x: 710,
      y: 330,
      goal: "Capturar datos minimos para operar (retiro/resultados segun intencion).",
      botReply:
        "Perfecto, te ayudo con eso. Me confirmas los datos minimos para avanzar?",
      userReply: "Entrega datos parciales o completos.",
      notes:
        "No repetir preguntas. Reusar captured_fields y contexto previo.",
    },
    {
      id: "fase_3_validacion_operativa",
      title: "Validacion operativa",
      x: 1030,
      y: 330,
      goal: "Validar coherencia y faltantes antes de confirmar.",
      botReply: "Gracias, valido los datos y te confirmo en un momento.",
      userReply: "Aclara dato faltante o confirma.",
      notes:
        "Si falta algo critico, volver a recogida de datos.",
    },
    {
      id: "fase_4_confirmacion_operativa",
      title: "Confirmacion operativa",
      x: 1350,
      y: 330,
      goal: "Confirmar resumen final antes de ejecutar o cerrar.",
      botReply: "Confirmas que estos son los datos correctos para continuar?",
      userReply: "Si / No (con correccion)",
      notes: "Si responde no, regresar a recogida/validacion.",
    },
    {
      id: "fase_6_cierre",
      title: "Cierre",
      x: 1670,
      y: 330,
      goal: "Cerrar con proximo paso claro y continuidad.",
      botReply:
        "Listo. Quedo gestionado. Si deseas, ahora te acompano con programacion de ruta o con cualquier otra consulta.",
      userReply: "Gracias / nueva consulta.",
      notes: "Si llega nueva intencion explicita, habilitar intent_switch.",
    },
    {
      id: "fase_7_escalado",
      title: "Escalado humano",
      x: 1670,
      y: 80,
      goal: "Escalar solo si hay bloqueo real o caso fuera de alcance.",
      botReply: "Te comunico con un asesor para ayudarte con este caso puntual.",
      userReply: "Expone caso especial o inconsistencia.",
      notes: "No escalar por dudas simples del formulario.",
    },
  ],
  transitions: [
    {
      id: "t-v3-1",
      from: "fase_0_bienvenida",
      to: "fase_1_clasificacion",
      trigger: "Usuario expresa necesidad",
      label: "Clasifica",
    },
    {
      id: "t-v3-2",
      from: "fase_1_clasificacion",
      to: "fase_registro_nuevo",
      trigger: "Intencion alta_cliente detectada",
      label: "Cliente nuevo",
    },
    {
      id: "t-v3-3",
      from: "fase_1_clasificacion",
      to: "fase_info_consulta",
      trigger: "Consulta informativa (analisis, precios, tiempos, alcance)",
      label: "Informa",
    },
    {
      id: "t-v3-4",
      from: "fase_1_clasificacion",
      to: "fase_gate_identificacion",
      trigger: "Intencion operativa (programacion, resultados operativos, gestion)",
      label: "Gate registro",
    },
    {
      id: "t-v3-5",
      from: "fase_gate_identificacion",
      to: "fase_2_recogida_datos_operativa",
      trigger: "Cliente identificado en base de datos",
      label: "Avanza operacion",
    },
    {
      id: "t-v3-6",
      from: "fase_gate_identificacion",
      to: "fase_registro_nuevo",
      trigger: "No identificado / no registrado",
      label: "Deriva registro",
    },
    {
      id: "t-v3-7",
      from: "fase_registro_nuevo",
      to: "fase_gate_identificacion",
      trigger: "Cliente confirma que ya completo el formulario",
      label: "Revalida",
    },
    {
      id: "t-v3-8",
      from: "fase_2_recogida_datos_operativa",
      to: "fase_3_validacion_operativa",
      trigger: "Datos minimos completos",
      label: "Valida",
    },
    {
      id: "t-v3-9",
      from: "fase_3_validacion_operativa",
      to: "fase_4_confirmacion_operativa",
      trigger: "Validacion correcta",
      label: "Confirma",
    },
    {
      id: "t-v3-10",
      from: "fase_4_confirmacion_operativa",
      to: "fase_6_cierre",
      trigger: "Usuario confirma",
      label: "Cierra",
    },
    {
      id: "t-v3-11",
      from: "fase_4_confirmacion_operativa",
      to: "fase_2_recogida_datos_operativa",
      trigger: "Usuario corrige informacion",
      label: "Corrige",
    },
    {
      id: "t-v3-12",
      from: "fase_info_consulta",
      to: "fase_1_clasificacion",
      trigger: "Cliente cambia a solicitud operativa",
      label: "Reclasifica",
    },
    {
      id: "t-v3-13",
      from: "fase_6_cierre",
      to: "fase_1_clasificacion",
      trigger: "Nueva solicitud en el mismo chat",
      label: "Nueva solicitud",
    },
    {
      id: "t-v4-15",
      from: "fase_1_clasificacion",
      to: "fase_contabilidad_pendiente",
      trigger: "Cliente solicita contabilidad",
      label: "Contabilidad",
    },
    {
      id: "t-v4-16",
      from: "fase_1_clasificacion",
      to: "fase_resultados_integracion_futura",
      trigger: "Cliente solicita resultados",
      label: "Resultados",
    },
    {
      id: "t-v4-17",
      from: "fase_contabilidad_pendiente",
      to: "fase_7_escalado",
      trigger: "Caso contable requiere asesor",
      label: "Escala conta",
    },
    {
      id: "t-v4-18",
      from: "fase_resultados_integracion_futura",
      to: "fase_info_consulta",
      trigger: "Consulta general sin identificador",
      label: "Info general",
    },
    {
      id: "t-v4-19",
      from: "fase_resultados_integracion_futura",
      to: "fase_6_cierre",
      trigger: "Estado informado correctamente",
      label: "Cierra resultado",
    },
    {
      id: "t-v3-14",
      from: "fase_info_consulta",
      to: "fase_7_escalado",
      trigger: "Caso excepcional fuera de alcance",
      label: "Escala",
    },
  ],
};

const state = loadState();
let selectedStageId = null;
let drag = null;

const board = document.getElementById("board");
const edgesSvg = document.getElementById("edges");
const selectionLabel = document.getElementById("selection-label");

const stageEmpty = document.getElementById("stage-empty");
const stageForm = document.getElementById("stage-form");
const stageIdInput = document.getElementById("stage-id");
const stageTitleInput = document.getElementById("stage-title");
const stageGoalInput = document.getElementById("stage-goal");
const stageBotInput = document.getElementById("stage-bot");
const stageUserInput = document.getElementById("stage-user");
const stageNotesInput = document.getElementById("stage-notes");

const transitionFrom = document.getElementById("transition-from");
const transitionTo = document.getElementById("transition-to");
const transitionTrigger = document.getElementById("transition-trigger");
const transitionLabel = document.getElementById("transition-label");
const transitionList = document.getElementById("transition-list");
const specOutput = document.getElementById("spec-output");

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return structuredClone(sampleData);
    }
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed.stages) || !Array.isArray(parsed.transitions)) {
      return structuredClone(sampleData);
    }
    return parsed;
  } catch {
    return structuredClone(sampleData);
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function nextStageId() {
  const base = "etapa";
  let idx = 1;
  while (state.stages.some((stage) => stage.id === `${base}_${idx}`)) {
    idx += 1;
  }
  return `${base}_${idx}`;
}

function nextTransitionId() {
  return `t-${Date.now()}-${Math.random().toString(16).slice(2, 6)}`;
}

function stageById(stageId) {
  return state.stages.find((stage) => stage.id === stageId) || null;
}

function drawBoard() {
  document.querySelectorAll(".stage-card").forEach((node) => node.remove());
  document.querySelectorAll(".edge-label").forEach((node) => node.remove());

  const rect = board.getBoundingClientRect();
  edgesSvg.setAttribute("width", String(Math.max(rect.width, board.scrollWidth)));
  edgesSvg.setAttribute("height", String(Math.max(rect.height, board.scrollHeight)));
  edgesSvg.querySelectorAll("path.edge").forEach((path) => path.remove());

  for (const stage of state.stages) {
    const card = document.createElement("article");
    card.className = "stage-card";
    if (stage.id === selectedStageId) {
      card.classList.add("selected");
    }
    card.style.left = `${stage.x}px`;
    card.style.top = `${stage.y}px`;
    card.dataset.stageId = stage.id;

    card.innerHTML = `
      <div class="stage-head">
        <div class="stage-id">${escapeHtml(stage.id)}</div>
        <div class="stage-title">${escapeHtml(stage.title || stage.id)}</div>
      </div>
      <div class="stage-content">
        <div><strong>Objetivo:</strong> ${escapeHtml(trimPreview(stage.goal))}</div>
        <div><strong>Bot:</strong> ${escapeHtml(trimPreview(stage.botReply))}</div>
        <div><strong>Usuario:</strong> ${escapeHtml(trimPreview(stage.userReply))}</div>
      </div>
    `;

    card.addEventListener("pointerdown", (event) => {
      drag = {
        stageId: stage.id,
        offsetX: event.clientX - stage.x,
        offsetY: event.clientY - stage.y,
      };
      card.setPointerCapture(event.pointerId);
    });

    card.addEventListener("click", () => {
      selectStage(stage.id);
    });

    board.appendChild(card);
  }

  for (const transition of state.transitions) {
    const from = stageById(transition.from);
    const to = stageById(transition.to);
    if (!from || !to) {
      continue;
    }

    const fromX = from.x + 130;
    const fromY = from.y + 110;
    const toX = to.x + 130;
    const toY = to.y;
    const c1X = fromX;
    const c1Y = fromY + 70;
    const c2X = toX;
    const c2Y = toY - 70;

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.classList.add("edge");
    path.setAttribute(
      "d",
      `M ${fromX} ${fromY} C ${c1X} ${c1Y}, ${c2X} ${c2Y}, ${toX} ${toY}`,
    );
    edgesSvg.appendChild(path);

    const label = document.createElement("div");
    label.className = "edge-label";
    label.textContent = transition.label || "Transicion";
    label.title = transition.trigger || "Sin trigger";
    label.style.left = `${(fromX + toX) / 2}px`;
    label.style.top = `${(fromY + toY) / 2}px`;
    board.appendChild(label);
  }
}

function trimPreview(value) {
  const text = (value || "").trim();
  if (!text) {
    return "-";
  }
  return text.length > 95 ? `${text.slice(0, 92)}...` : text;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function selectStage(stageId) {
  selectedStageId = stageId;
  const stage = stageById(stageId);
  if (!stage) {
    stageForm.classList.add("hidden");
    stageEmpty.classList.remove("hidden");
    selectionLabel.textContent = "Sin etapa seleccionada";
    drawBoard();
    return;
  }

  stageForm.classList.remove("hidden");
  stageEmpty.classList.add("hidden");
  selectionLabel.textContent = `Etapa seleccionada: ${stage.id}`;

  stageIdInput.value = stage.id || "";
  stageTitleInput.value = stage.title || "";
  stageGoalInput.value = stage.goal || "";
  stageBotInput.value = stage.botReply || "";
  stageUserInput.value = stage.userReply || "";
  stageNotesInput.value = stage.notes || "";
  drawBoard();
}

function syncStageEditor() {
  if (!selectedStageId) {
    return;
  }

  const stage = stageById(selectedStageId);
  if (!stage) {
    return;
  }

  const nextId = normalizeId(stageIdInput.value);
  if (!nextId) {
    return;
  }

  if (nextId !== stage.id && state.stages.some((item) => item.id === nextId)) {
    stageIdInput.setCustomValidity("Esta clave ya existe");
    stageIdInput.reportValidity();
    return;
  }
  stageIdInput.setCustomValidity("");

  const previousId = stage.id;
  stage.id = nextId;
  stage.title = stageTitleInput.value.trim();
  stage.goal = stageGoalInput.value.trim();
  stage.botReply = stageBotInput.value.trim();
  stage.userReply = stageUserInput.value.trim();
  stage.notes = stageNotesInput.value.trim();

  if (previousId !== nextId) {
    for (const transition of state.transitions) {
      if (transition.from === previousId) {
        transition.from = nextId;
      }
      if (transition.to === previousId) {
        transition.to = nextId;
      }
    }
    selectedStageId = nextId;
  }

  saveState();
  rebuildTransitionSelects();
  drawBoard();
}

function normalizeId(value) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function rebuildTransitionSelects() {
  const options = state.stages
    .map((stage) => `<option value="${escapeHtml(stage.id)}">${escapeHtml(stage.id)}</option>`)
    .join("");
  transitionFrom.innerHTML = options;
  transitionTo.innerHTML = options;
}

function renderTransitionList() {
  transitionList.innerHTML = "";
  if (!state.transitions.length) {
    transitionList.textContent = "Sin transiciones";
    return;
  }

  for (const transition of state.transitions) {
    const item = document.createElement("div");
    item.className = "transition-item";
    item.innerHTML = `
      <div class="transition-head">
        <strong>${escapeHtml(transition.from)} -> ${escapeHtml(transition.to)}</strong>
        <button type="button" data-transition-id="${escapeHtml(transition.id)}" class="danger">Borrar</button>
      </div>
      <div><b>Trigger:</b> ${escapeHtml(transition.trigger || "-")}</div>
      <div><b>Etiqueta:</b> ${escapeHtml(transition.label || "-")}</div>
    `;
    transitionList.appendChild(item);
  }
}

function addStage() {
  const id = nextStageId();
  const newStage = {
    id,
    title: `Nueva etapa ${state.stages.length + 1}`,
    x: 120 + ((state.stages.length % 4) * 290),
    y: 140 + (Math.floor(state.stages.length / 4) * 230),
    goal: "",
    botReply: "",
    userReply: "",
    notes: "",
  };
  state.stages.push(newStage);
  saveState();
  rebuildTransitionSelects();
  renderTransitionList();
  selectStage(newStage.id);
}

function duplicateStage() {
  if (!selectedStageId) {
    return;
  }
  const stage = stageById(selectedStageId);
  if (!stage) {
    return;
  }

  const copy = {
    ...stage,
    id: nextStageId(),
    title: `${stage.title} (copia)`,
    x: stage.x + 40,
    y: stage.y + 40,
  };
  state.stages.push(copy);
  saveState();
  rebuildTransitionSelects();
  renderTransitionList();
  selectStage(copy.id);
}

function deleteStage() {
  if (!selectedStageId) {
    return;
  }
  const target = selectedStageId;
  state.stages = state.stages.filter((stage) => stage.id !== target);
  state.transitions = state.transitions.filter(
    (transition) => transition.from !== target && transition.to !== target,
  );
  selectedStageId = null;
  saveState();
  rebuildTransitionSelects();
  renderTransitionList();
  selectStage(null);
}

function saveTransition() {
  const from = transitionFrom.value;
  const to = transitionTo.value;
  const trigger = transitionTrigger.value.trim();
  const label = transitionLabel.value.trim();
  if (!from || !to) {
    return;
  }

  state.transitions.push({
    id: nextTransitionId(),
    from,
    to,
    trigger,
    label,
  });
  transitionTrigger.value = "";
  transitionLabel.value = "";
  saveState();
  drawBoard();
  renderTransitionList();
}

function deleteTransition(transitionId) {
  state.transitions = state.transitions.filter((transition) => transition.id !== transitionId);
  saveState();
  drawBoard();
  renderTransitionList();
}

function autoLayout() {
  const columns = 4;
  const xStart = 70;
  const yStart = 80;
  const xGap = 300;
  const yGap = 240;

  state.stages.forEach((stage, index) => {
    stage.x = xStart + (index % columns) * xGap;
    stage.y = yStart + Math.floor(index / columns) * yGap;
  });
  saveState();
  drawBoard();
}

function exportJson() {
  const payload = JSON.stringify(state, null, 2);
  const blob = new Blob([payload], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `flow-lab-${new Date().toISOString().slice(0, 19).replaceAll(":", "-")}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function importJson(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const parsed = JSON.parse(String(reader.result || "{}"));
      if (!Array.isArray(parsed.stages) || !Array.isArray(parsed.transitions)) {
        throw new Error("Formato invalido");
      }
      state.stages = parsed.stages;
      state.transitions = parsed.transitions;
      selectedStageId = null;
      saveState();
      rebuildTransitionSelects();
      renderTransitionList();
      selectStage(null);
    } catch {
      alert("No pude importar ese JSON. Revisa el formato.");
    }
    event.target.value = "";
  };
  reader.readAsText(file);
}

function resetDemo() {
  state.stages = structuredClone(sampleData.stages);
  state.transitions = structuredClone(sampleData.transitions);
  selectedStageId = null;
  saveState();
  rebuildTransitionSelects();
  renderTransitionList();
  selectStage(null);
}

function generateSpec() {
  const lines = [];
  lines.push("# Borrador de flujo conversacional");
  lines.push("");
  lines.push("## Etapas");
  for (const stage of state.stages) {
    lines.push(`- ${stage.id} (${stage.title || "Sin nombre"})`);
    if (stage.goal) {
      lines.push(`  objetivo: ${stage.goal}`);
    }
    if (stage.botReply) {
      lines.push(`  bot_esperado: ${stage.botReply}`);
    }
    if (stage.userReply) {
      lines.push(`  usuario_esperado: ${stage.userReply}`);
    }
    if (stage.notes) {
      lines.push(`  notas: ${stage.notes}`);
    }
  }
  lines.push("");
  lines.push("## Transiciones");
  for (const transition of state.transitions) {
    lines.push(
      `- ${transition.from} -> ${transition.to} | trigger: ${transition.trigger || "-"} | etiqueta: ${transition.label || "-"}`,
    );
  }
  specOutput.value = lines.join("\n");
}

board.addEventListener("pointermove", (event) => {
  if (!drag) {
    return;
  }
  const stage = stageById(drag.stageId);
  if (!stage) {
    return;
  }

  stage.x = Math.max(0, event.clientX - drag.offsetX);
  stage.y = Math.max(0, event.clientY - drag.offsetY);
  drawBoard();
});

board.addEventListener("pointerup", () => {
  if (!drag) {
    return;
  }
  drag = null;
  saveState();
});

stageForm.addEventListener("input", syncStageEditor);
transitionList.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLButtonElement)) {
    return;
  }
  const transitionId = target.dataset.transitionId;
  if (!transitionId) {
    return;
  }
  deleteTransition(transitionId);
});

document.getElementById("btn-add-stage").addEventListener("click", addStage);
document.getElementById("btn-add-transition").addEventListener("click", () => {
  transitionTrigger.focus();
});
document.getElementById("btn-layout").addEventListener("click", autoLayout);
document.getElementById("btn-export").addEventListener("click", exportJson);
document.getElementById("btn-reset").addEventListener("click", resetDemo);
document.getElementById("import-file").addEventListener("change", importJson);
document.getElementById("btn-save-transition").addEventListener("click", saveTransition);
document.getElementById("btn-delete-stage").addEventListener("click", deleteStage);
document.getElementById("btn-duplicate-stage").addEventListener("click", duplicateStage);
document.getElementById("btn-generate-spec").addEventListener("click", generateSpec);

rebuildTransitionSelects();
renderTransitionList();
selectStage(state.stages[0]?.id || null);
