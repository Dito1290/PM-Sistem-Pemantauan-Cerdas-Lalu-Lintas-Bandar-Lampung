"""Flask CLI commands.

    flask --app wsgi users create --username admin --email admin@example.org --role admin
    flask --app wsgi ingest run
    flask --app wsgi stats aggregate [--hour 2026-10-22T09:00:00Z | --from ... --to ...]
"""
from __future__ import annotations

from datetime import datetime

import click
from flask import Flask, current_app
from flask.cli import AppGroup
from sqlalchemy import func, select

from .auth.passwords import hash_password
from .extensions import db
from .models import ROLES, User

users_cli = AppGroup("users", help="Manage user accounts.")
ingest_cli = AppGroup("ingest", help="CCTV stream ingest service.")
stats_cli = AppGroup("stats", help="Statistics aggregation.")


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise click.BadParameter("Timestamp must include a timezone offset, e.g. 2026-10-22T09:00:00+07:00")
    return parsed


@users_cli.command("create")
@click.option("--username", required=True)
@click.option("--email", required=True)
@click.option("--role", type=click.Choice(ROLES), required=True)
@click.password_option(help="Prompted if omitted; never put real passwords in scripts.")
def create_user(username: str, email: str, role: str, password: str) -> None:
    username, email = username.strip(), email.strip().lower()
    exists = db.session.scalar(select(User).where(
        (func.lower(User.username) == username.lower()) | (func.lower(User.email) == email)
    ))
    if exists:
        raise click.ClickException("Username or email already exists.")
    try:
        password_hash = hash_password(password)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    db.session.add(User(username=username, email=email, role=role, password_hash=password_hash))
    db.session.commit()
    click.echo(f"Created {role} '{username}'.")


@users_cli.command("set-password")
@click.option("--username", required=True)
@click.password_option()
def set_password(username: str, password: str) -> None:
    user = db.session.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if user is None:
        raise click.ClickException("User not found.")
    try:
        user.password_hash = hash_password(password)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    db.session.commit()
    click.echo("Password updated.")


@ingest_cli.command("run")
def run_ingest() -> None:
    """Run the stream readers in the foreground (one thread per active camera)."""
    from .ingest import IngestSupervisor

    supervisor = IngestSupervisor(current_app._get_current_object())
    supervisor.install_signal_handlers()
    supervisor.run_forever()


@stats_cli.command("aggregate")
@click.option("--hour", help="Aggregate one hour (ISO timestamp with offset).")
@click.option("--from", "start", help="Backfill start (inclusive).")
@click.option("--to", "end", help="Backfill end (exclusive).")
def aggregate(hour: str | None, start: str | None, end: str | None) -> None:
    """Without options: aggregate the most recent completed hour(s)."""
    from .services import stats_service

    if hour:
        rows = stats_service.aggregate_hour(_aware(hour))
        click.echo(f"{rows} camera row(s) written.")
    elif start and end:
        hours = stats_service.aggregate_range(_aware(start), _aware(end))
        click.echo(f"{hours} hour(s) aggregated.")
    elif start or end:
        raise click.UsageError("--from and --to must be used together.")
    else:
        click.echo("Aggregated: " + ", ".join(stats_service.aggregate_recent()))


def register_cli(app: Flask) -> None:
    app.cli.add_command(users_cli)
    app.cli.add_command(ingest_cli)
    app.cli.add_command(stats_cli)
