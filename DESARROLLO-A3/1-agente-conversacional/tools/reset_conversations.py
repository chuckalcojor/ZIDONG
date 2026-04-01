from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import settings
from app.services.supabase_service import SupabaseService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resetea estado conversacional del bot en Supabase."
    )
    parser.add_argument(
        "--chat-id",
        dest="chat_id",
        default="",
        help="External chat id especifico para resetear una sola conversacion.",
    )
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Tambien borra historial de mensajes y eventos de etapas.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    supabase = SupabaseService(settings.supabase_url, settings.supabase_service_role_key)

    if args.chat_id:
        session_filter = {"external_chat_id": f"eq.{args.chat_id}"}
        events_filter = {"external_chat_id": f"eq.{args.chat_id}"}
    else:
        session_filter = {"external_chat_id": "not.is.null"}
        events_filter = {"external_chat_id": "not.is.null"}

    sessions_deleted = supabase.delete_rows("telegram_sessions", session_filter)
    print(f"telegram_sessions eliminadas: {sessions_deleted}")

    if args.full_history:
        try:
            stage_events_deleted = supabase.delete_rows("conversation_stage_events", events_filter)
            print(f"conversation_stage_events eliminadas: {stage_events_deleted}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                print("conversation_stage_events no existe en este entorno, se omite.")
            else:
                raise

        try:
            message_events_deleted = supabase.delete_rows("telegram_message_events", events_filter)
            print(f"telegram_message_events eliminadas: {message_events_deleted}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                print("telegram_message_events no existe en este entorno, se omite.")
            else:
                raise


if __name__ == "__main__":
    main()
