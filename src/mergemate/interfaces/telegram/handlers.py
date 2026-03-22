"""Telegram command and message handlers."""

from telegram import Update
from telegram.ext import ContextTypes

from mergemate.interfaces.telegram.models import TelegramRequest
from mergemate.interfaces.telegram.presenter import (
    format_approval_started,
    format_approval_not_needed,
    format_auto_execution_started,
    format_cancelled,
    format_completion,
    format_detailed_status,
    format_failure,
    format_plan_for_confirmation,
    format_welcome,
)
from mergemate.interfaces.telegram.progress_notifier import watch_run_progress


def _runtime(context: ContextTypes.DEFAULT_TYPE):
    return context.application.bot_data["runtime"]


def _start_progress_watcher(application, runtime, chat_id: int, run_id: str) -> None:
    application.create_task(watch_run_progress(application, runtime, chat_id, run_id))


def _build_request(update: Update, runtime) -> TelegramRequest:
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    assert message is not None
    assert user is not None
    assert chat is not None
    return TelegramRequest(
        chat_id=chat.id,
        user_id=user.id,
        message_text=message.text or "",
        agent_name=runtime.settings.default_agent,
    )


async def _notify_terminal_update(application, chat_id: int, run) -> None:
    if run.status.value == "completed":
        text = format_completion(run.run_id, run.result_text or "")
    elif run.status.value == "cancelled":
        text = format_cancelled(run.run_id)
    else:
        text = format_failure(run.run_id, run.error_text)
    await application.bot.send_message(chat_id=chat_id, text=text)


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
    await message.reply_text(format_detailed_status(run))


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
        on_finished=lambda completed_run: _notify_terminal_update(
            context.application,
            chat.id,
            completed_run,
        ),
    )
    if run is None:
        await message.reply_text("Run approval failed.")
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
    await message.reply_text(format_cancelled(run.run_id))


async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    runtime = _runtime(context)
    request = _build_request(update, runtime)
    message = update.effective_message
    if message is None or not request.message_text.strip():
        return

    latest_run = runtime.get_run_status.execute(chat_id=request.chat_id)
    if latest_run is not None and latest_run.status.value == "awaiting_confirmation":
        revised = await runtime.submit_prompt.revise_plan(latest_run.run_id, request.message_text)
        if revised is None:
            await message.reply_text("Could not revise the current plan.")
            return
        await message.reply_text(
            format_plan_for_confirmation(
                revised.run_id,
                runtime.settings.workflow_control.planner_agent_name,
                revised.plan_text or "",
                revised.estimate_seconds,
            )
        )
        return

    agent_config = runtime.settings.agents.get(request.agent_name)
    workflow = agent_config.workflow if agent_config is not None else "generate_code"
    submit_result = await runtime.submit_prompt.execute(
        chat_id=request.chat_id,
        user_id=request.user_id,
        agent_name=request.agent_name,
        workflow=workflow,
        prompt=request.message_text,
        on_finished=lambda run: _notify_terminal_update(context.application, request.chat_id, run),
    )
    if submit_result.status != "awaiting_confirmation":
        await message.reply_text(
            format_auto_execution_started(
                submit_result.run_id,
                submit_result.plan_text or "",
                submit_result.estimate_seconds,
            )
        )
        _start_progress_watcher(context.application, runtime, request.chat_id, submit_result.run_id)
        return
    await message.reply_text(
        format_plan_for_confirmation(
            submit_result.run_id,
            runtime.settings.workflow_control.planner_agent_name,
            submit_result.plan_text or "",
            submit_result.estimate_seconds,
        )
    )