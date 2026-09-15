"""Generate synthetic Zendesk-like tickets for the prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_PATH = REPO_ROOT / "data" / "tickets" / "synthetic_tickets.jsonl"

TEMPLATES: list[dict] = [
    {
        "ticket_id": "RGT-00101",
        "player_id": "abc123",
        "category": "vanguard_error",
        "routing_branch": "tecnica",
        "subcategory": "VAN_57",
        "subject": "VAN 57 error al iniciar Valorant",
        "body": "Cada vez que abro el juego me aparece VAN 57 y no entra a la pantalla de inicio.",
        "priority": "medium",
        "action": "close",
        "response_draft": "Hola, VAN 57 suele resolverse reparando Vanguard y reiniciando Windows. Prueba esos pasos y responde si persiste.",
        "mins": 8,
    },
    {
        "ticket_id": "RGT-00102",
        "player_id": "abc123",
        "category": "vanguard_error",
        "routing_branch": "tecnica",
        "subcategory": "VAN_9006",
        "subject": "VAN 9006 después de actualizar Windows",
        "body": "Tras el update me sale VAN 9006. Ya reinstale el cliente y sigue fallando.",
        "priority": "high",
        "action": "escalate",
        "response_draft": "Hola, VAN 9006 a veces queda tras reinstalación. Escalamos con tus logs de Vanguard.",
        "mins": 20,
    },
    {
        "ticket_id": "RGT-00103",
        "player_id": "abc123",
        "category": "vanguard_error",
        "routing_branch": "tecnica",
        "subcategory": "crash",
        "subject": "El cliente se cierra en el menú",
        "body": "Crash al abrir el cliente de Riot. Lag previo y luego cierra.",
        "priority": "medium",
        "action": "close",
        "response_draft": "Hola, verifica archivos, actualiza GPU y excluye Riot del antivirus.",
        "mins": 10,
    },
    {
        "ticket_id": "RGT-00104",
        "player_id": "abc123",
        "category": "vanguard_error",
        "routing_branch": "tecnica",
        "subcategory": "VAN_128",
        "subject": "VAN 128 con overlay de Discord",
        "body": "Error VAN 128 cuando tengo Discord overlay. Vanguard no arranca.",
        "priority": "low",
        "action": "close",
        "response_draft": "Hola, desactiva overlays y prueba un arranque limpio de Windows.",
        "mins": 6,
    },
    {
        "ticket_id": "RGT-00105",
        "player_id": "abc123",
        "category": "vanguard_error",
        "routing_branch": "tecnica",
        "subcategory": "VAN_2266",
        "subject": "VAN 2266 en portátil nuevo",
        "body": "Portátil nuevo, Secure Boot on, igual VAN 2266 al iniciar.",
        "priority": "medium",
        "action": "close",
        "response_draft": "Hola, confirma TPM 2.0 y repara Vanguard desde el instalador.",
        "mins": 9,
    },
    {
        "ticket_id": "RGT-00201",
        "player_id": "banned42",
        "category": "ban_penalty",
        "routing_branch": "penalizaciones",
        "subcategory": "ban_permanente",
        "subject": "Ban permanente injusto",
        "body": "Me banearon permanente y no uso cheats. Quiero que revisen el ban.",
        "priority": "high",
        "action": "close",
        "response_draft": "Hola, el ban permanente de esta cuenta no es apelable según la herramienta interna. No podemos restaurar el acceso.",
        "mins": 12,
    },
    {
        "ticket_id": "RGT-00202",
        "player_id": "appeal99",
        "category": "ban_penalty",
        "routing_branch": "penalizaciones",
        "subcategory": "apelacion",
        "subject": "Quiero apelar mi ban",
        "body": "Me banearon permanente. Entiendo que hay apelación. player_id=appeal99",
        "priority": "high",
        "action": "escalate",
        "response_draft": "Hola, tu sanción figura como apelable. Escalamos el caso al equipo de revisión.",
        "mins": 25,
    },
    {
        "ticket_id": "RGT-00203",
        "player_id": "tempban7",
        "category": "ban_penalty",
        "routing_branch": "penalizaciones",
        "subcategory": "suspension",
        "subject": "Suspensión de chat",
        "body": "Tengo una penalización / suspensión temporal de chat. ¿Cuánto falta?",
        "priority": "low",
        "action": "close",
        "response_draft": "Hola, la suspensión temporal termina sola. No hay forma de acortar el tiempo.",
        "mins": 5,
    },
    {
        "ticket_id": "RGT-00204",
        "player_id": "abc123",
        "category": "ban_penalty",
        "routing_branch": "penalizaciones",
        "subcategory": "cuenta_robada",
        "subject": "Creo que me hackearon la cuenta",
        "body": "Cambios raros de email. Posible cuenta robada y ban asociado.",
        "priority": "high",
        "action": "escalate",
        "response_draft": "Hola, por indicios de hijack escalamos a recuperación de cuenta.",
        "mins": 30,
    },
    {
        "ticket_id": "RGT-00205",
        "player_id": "banned42",
        "category": "ban_penalty",
        "routing_branch": "penalizaciones",
        "subcategory": "ban_permanente",
        "subject": "¿Puedo crear otra cuenta?",
        "body": "Me banearon permanente. ¿Puedo eludir la penalización con otra cuenta?",
        "priority": "medium",
        "action": "close",
        "response_draft": "Hola, evadir un ban creando otra cuenta viola las reglas y puede extender la sanción.",
        "mins": 7,
    },
    {
        "ticket_id": "RGT-00301",
        "player_id": "buyer55",
        "category": "purchase_billing",
        "routing_branch": "billing",
        "subcategory": "refund",
        "subject": "Reembolso de Riot Points",
        "body": "Quiero un reembolso de mis Riot Points de la compra de skins.",
        "priority": "medium",
        "action": "close",
        "response_draft": "Hola, esta cuenta ya usó el cupo de reembolso. No aplica otro reembolso de RP.",
        "mins": 11,
    },
    {
        "ticket_id": "RGT-00302",
        "player_id": "fraud01",
        "category": "purchase_billing",
        "routing_branch": "billing",
        "subcategory": "unrecognized",
        "subject": "Cargo que no reconozco",
        "body": "Hay un cargo duplicado / no reconozco la compra de RP. player_id=fraud01",
        "priority": "high",
        "action": "escalate",
        "response_draft": "Hola, por compra no reconocida escalamos a fraude/billing.",
        "mins": 22,
    },
    {
        "ticket_id": "RGT-00303",
        "player_id": "buyer55",
        "category": "purchase_billing",
        "routing_branch": "billing",
        "subcategory": "missing_skin",
        "subject": "No me llegó la skin",
        "body": "Pagué el bundle y no veo la skin en el inventario. Revisa la compra.",
        "priority": "medium",
        "action": "close",
        "response_draft": "Hola, la compra del bundle figura en el historial. Reinicia el cliente para refrescar el inventario.",
        "mins": 8,
    },
    {
        "ticket_id": "RGT-00304",
        "player_id": "abc123",
        "category": "purchase_billing",
        "routing_branch": "billing",
        "subcategory": "rp",
        "subject": "No recibí los RP",
        "body": "Compré Riot Points y no se acreditaron. ¿Pueden revisar el billing?",
        "priority": "medium",
        "action": "close",
        "response_draft": "Hola, vemos RP-1000 acreditado el 20 ago. Si no aparecen, reloguea.",
        "mins": 9,
    },
    {
        "ticket_id": "RGT-00305",
        "player_id": "buyer55",
        "category": "purchase_billing",
        "routing_branch": "billing",
        "subcategory": "refund",
        "subject": "Segundo reembolso",
        "body": "Quiero otro reembolso de una skin. Ya pedí uno antes.",
        "priority": "low",
        "action": "close",
        "response_draft": "Hola, el cupo de reembolso ya fue utilizado.",
        "mins": 6,
    },
]


def as_ticket(row: dict) -> dict:
    return {
        "ticket_id": row["ticket_id"],
        "player_id": row["player_id"],
        "category": row["category"],
        "routing_branch": row["routing_branch"],
        "subcategory": row["subcategory"],
        "subject": row["subject"],
        "body": row["body"],
        "language": "es",
        "priority": row["priority"],
        "created_at": "2026-09-01T10:00:00Z",
        "resolution": {
            "response_draft": row["response_draft"],
            "action": row["action"],
            "resolution_time_mins": row["mins"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in TEMPLATES:
            handle.write(json.dumps(as_ticket(row), ensure_ascii=False) + "\n")
    print(f"Wrote {len(TEMPLATES)} tickets to {args.out}")


if __name__ == "__main__":
    main()
