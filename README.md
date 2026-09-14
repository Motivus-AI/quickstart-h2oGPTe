<p align="center">
  <a href="https://en.wikipedia.org/wiki/Riot_Games#/media/File:Riot_Games_2022.svg">
    <img src="assets/riot-games-2022.svg" alt="Riot Games" height="56">
  </a>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <a href="https://docs.h2o.ai/">
    <img src="assets/h2o-logo.svg" alt="H2O.ai" height="72">
  </a>
</p>

# Riot Games Support Agent

## h2oGPTe Helpdesk Assistant

Agente de IA que asiste a los agentes humanos de soporte de Riot Games a responder tickets más rápido usando h2oGPTe con RAG, Function Calling y Routing.

## Caso de uso

Los agentes humanos de soporte reciben decenas de tickets diarios. Este agente:

1. **Clasifica** el ticket entrante automáticamente
2. **Busca** en la base de conocimiento de Riot la solución más relevante (RAG)
3. **Propone** un borrador de respuesta listo para editar y enviar
4. **Sugiere** si el ticket se puede cerrar o necesita escalarse a un humano

El agente humano mantiene el control final, el LLM solo hace el trabajo pesado.
