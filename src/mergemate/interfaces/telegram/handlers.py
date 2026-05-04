"""Telegram command and message handlers."""

from telegram import Update
from telegram.ext import ContextTypes

from mergemate.application.use_cases.submit_prompt import PromptSubmissionError
from mergemate.domain.shared import is_user_facing_workflow
from mergemate.interfaces.telegram import message_utils
from mergemate.interfaces.telegram.models import TelegramRequest
from mergemate.interfaces.telegram.presenter import (
    format_acknowledgement,
    format_approval_started,
    format_approval_not_needed,
    format_cancellation_not_allowed,
    format_cancelled,
    format_detailed_status,
    format_plan_for_confirmation,
    format_planning_in_progress,
    format_tool_history,
    format_welcome,
)
from mergemate.interfaces.telegram.progress_notifier import notify_terminal_update, start_progress_watcher


TELEGRAM_MESSAGE_LIMIT = message_utils.TELEGRAM_MESSAGE_LIMIT
MAX_TOOL_HISTORY_LIMIT = 50


def _runtime(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["runtime"]


def _start_progress_watcher(application, runtime, chat_id: int, run_id: str) -> None:
    start_progress_watcher(application, runtime, chat_id, run_id)


async def _notify_terminal_update(application, chat_id: int, run) -> None:
    await notify_terminal_update(application, chat_id, run)


def _is_chat_entry_agent(runtime, agent_name: str) -> bool:
    agent_config = runtime.settings.agents.get(agent_name)
    return agent_config is not None and is_user_facing_workflow(agent_config.workflow)


def _build_request(update: Update, runtime) -> TelegramRequest | None:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if message is None or user is None or chat is None:
        return None
    if not _is_chat_entry_agent(runtime, runtime.settings.default_agent):
        return None
    return TelegramRequest(
        chat_id=chat.id,
        user_id=user.id,
        message_text=message.text or "",
        agent_name=runtime.settings.default_agent,
    )


def _parse_tools_command_args(args: list[str]) -> tuple[str | None, int, str | None]:
    limit_error = (
        f"Usage: /tools [run_id] [limit]. Limit must be a positive integer up to {MAX_TOOL_HISTORY_LIMIT}."
    )

    def _parse_limit(raw_value: str) -> int | None:
        if not raw_value.isdigit():
            return None
        parsed_limit = int(raw_value)
        if parsed_limit <= 0 or parsed_limit > MAX_TOOL_HISTORY_LIMIT:
            return None
        return parsed_limit

    if not args:
        return None, 10, None
    if len(args) == 1:
        limit = _parse_limit(args[0])
        if limit is not None:
            return None, limit, None
        if args[0].isdigit():
            return None, 10, limit_error
        return args[0], 10, None
    if len(args) == 2:
        limit = _parse_limit(args[1])
        if limit is None:
            return None, 10, limit_error
        return args[0], limit, None
    return None, 10, "Usage: /tools [run_id] [limit]."


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = _runtime(context)
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(format_welcome(runtime.settings.default_agent))


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = _runtime(context)
    chat = update.effective_chat
    message = update.effective_message
    if chat is None or message is None:
        return

    run_id = context.args[0] if context.args else None
    run = runtime.get_run_status.execute(run_id, chat_id=chat.id)
    if run is None:
        await message.reply_text("No runs found for this chat.")
        return
    await message_utils.send_text_chunks(message.reply_text, format_detailed_status(run))


async def tools_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = _runtime(context)
    chat = update.effective_chat
    message = update.effective_message
    if chat is None or message is None:
        return

    run_id, limit, error_message = _parse_tools_command_args(context.args or [])
    if error_message is not None:
        await message.reply_text(error_message)
        return
    run = runtime.get_run_status.execute(run_id, chat_id=chat.id, tool_event_limit=limit)
    if run is None:
        await message.reply_text("No runs found for this chat.")
        return
    await message_utils.send_text_chunks(message.reply_text, format_tool_history(run))


async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = _runtime(context)
    chat = update.effective_chat
    message = update.effective_message
    if chat is None or message is None:
        return

    run_id = context.args[0] if context.args else None
    if run_id is None:
        latest = runtime.get_run_status.execute(chat_id=chat.id)
        run_id = latest.run_id if latest is not None else None
    if run_id is None:
        await message.reply_text("No run is available to approve.")
        return

    run = runtime.approve_run.execute(
        run_id,
        chat_id=chat.id,
    )
    if run is None:
        await message.reply_text("Run approval failed.")
        return
    if not run.dispatched and getattr(run, "error_text", None):
        await message_utils.send_text_chunks(message.reply_text, run.error_text)
        return
    if not run.dispatched:
        await message.reply_text(format_approval_not_needed(run.run_id, run.status))
        return
    await message.reply_text(format_approval_started(run.run_id))
    _start_progress_watcher(context.application, runtime, chat.id, run.run_id)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = _runtime(context)
    chat = update.effective_chat
    message = update.effective_message
    if chat is None or message is None:
        return

    run_id = context.args[0] if context.args else None
    run = runtime.cancel_run.execute(run_id, chat_id=chat.id)
    if run is None:
        await message.reply_text("No run could be cancelled.")
        return
    if not run.cancelled:
        await message.reply_text(format_cancellation_not_allowed(run.run_id, run.status))
        return
    await message.reply_text(format_cancelled(run.run_id))


async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = _runtime(context)
    message = update.effective_message
    request = _build_request(update, runtime)
    if message is None:
        return
    if request is None:
        if not _is_chat_entry_agent(runtime, runtime.settings.default_agent):
            await message.reply_text(
                "The configured default agent is not available for Telegram chat entry. "
                "Use generate_code, debug_code, or explain_code as the default agent workflow."
            )
        return
    if not request.message_text.strip():
        return

    latest_run = runtime.get_run_status.execute(chat_id=request.chat_id)
    if latest_run is not None and latest_run.status.value == "awaiting_confirmation":
        if not latest_run.plan_text:
            await message.reply_text(format_planning_in_progress(latest_run.run_id))
            return
        try:
            revised = await runtime.submit_prompt.revise_plan_for_chat(
                latest_run.run_id,
                request.message_text,
                chat_id=request.chat_id,
            )
        except PromptSubmissionError as exc:
            failed_run = runtime.get_run_status.execute(exc.run_id, chat_id=request.chat_id)
            error_text = failed_run.error_text if failed_run is not None and failed_run.error_text else exc.error_text
            await message_utils.send_text_chunks(message.reply_text, error_text)
            return
        if revised is None:
            await message.reply_text("Could not revise the current plan.")
            return
        await message_utils.send_text_chunks(
            message.reply_text,
            format_plan_for_confirmation(
                revised.run_id,
                runtime.settings.resolve_agent_name_for_workflow("planning"),
                revised.plan_text or "",
                revised.estimate_seconds,
            )
        )
        return

    agent_config = runtime.settings.agents.get(request.agent_name)
    workflow = agent_config.workflow if agent_config is not None else "generate_code"
    try:
        submit_result = await runtime.submit_prompt.execute(
            chat_id=request.chat_id,
            user_id=request.user_id,
            agent_name=request.agent_name,
            workflow=workflow,
            prompt=request.message_text,
        )
    except PromptSubmissionError as exc:
        failed_run = runtime.get_run_status.execute(exc.run_id, chat_id=request.chat_id)
        error_text = failed_run.error_text if failed_run is not None and failed_run.error_text else exc.error_text
        await message_utils.send_text_chunks(message.reply_text, error_text)
        return
    await message_utils.send_text_chunks(
        message.reply_text,
        format_acknowledgement(
            submit_result.run_id,
            request.agent_name,
            submit_result.estimate_seconds,
        ),
    )

    # Continue planning in background and notify when plan is ready.
    async def _continue_planning() -> None:
        try:
            completed = await runtime.submit_prompt.complete_planning(
                submit_result.run_id,
                on_finished=lambda result: None,
            )
        except PromptSubmissionError:
            return
        if completed is not None and completed.plan_text:
            await context.application.bot.send_message(
                chat_id=request.chat_id,
                text=format_plan_for_confirmation(
                    completed.run_id,
                    runtime.settings.resolve_agent_name_for_workflow("planning"),
                    completed.plan_text,
                    completed.estimate_seconds,
                ),
            )

    context.application.create_task(_continue_planning())