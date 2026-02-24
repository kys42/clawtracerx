#!/usr/bin/env python3
"""
ClawTracerX — OpenClaw Agent Monitor

Usage:
  ctrace sessions [--agent NAME] [--last N] [--type TYPE]
  ctrace analyze SESSION [--no-subagents]
  ctrace raw SESSION --turn N
  ctrace crons [--last N] [--job ID]
  ctrace subagents [--parent SESSION] [--last N]
  ctrace cost [--period PERIOD] [--agent NAME]
  ctrace context SESSION
  ctrace web [--port PORT]
"""

import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="ctrace",
        description="ClawTracerX — Analyze agent sessions, tool calls, and costs",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # sessions
    p_sessions = subparsers.add_parser("sessions", aliases=["ls"], help="List sessions")
    p_sessions.add_argument("--agent", "-a", default="all", help="Agent ID or 'all'")
    p_sessions.add_argument("--last", "-n", type=int, default=20, help="Number of sessions")
    p_sessions.add_argument("--type", "-t", dest="session_type", choices=["cron", "heartbeat", "chat", "subagent"], help="Filter by type")

    # analyze
    p_analyze = subparsers.add_parser("analyze", aliases=["a"], help="Analyze a session")
    p_analyze.add_argument("session", help="Session ID, path, or agent:id")
    p_analyze.add_argument("--no-subagents", action="store_true", help="Skip recursive subagent parsing")

    # raw
    p_raw = subparsers.add_parser("raw", help="Show raw JSONL for a turn")
    p_raw.add_argument("session", help="Session ID, path, or agent:id")
    p_raw.add_argument("--turn", "-t", type=int, required=True, help="Turn index")

    # crons
    p_crons = subparsers.add_parser("crons", help="Show cron run history")
    p_crons.add_argument("--last", "-n", type=int, default=20, help="Number of runs")
    p_crons.add_argument("--job", "-j", help="Filter by job ID")

    # subagents
    p_sub = subparsers.add_parser("subagents", aliases=["sub"], help="Show subagent runs")
    p_sub.add_argument("--parent", "-p", help="Filter by parent session")
    p_sub.add_argument("--last", "-n", type=int, default=20, help="Number of runs")

    # cost
    p_cost = subparsers.add_parser("cost", help="Show cost summary")
    p_cost.add_argument("--period", default="today", choices=["today", "week", "month", "all"], help="Time period")
    p_cost.add_argument("--agent", "-a", default="all", help="Agent ID or 'all'")

    # context
    p_context = subparsers.add_parser("context", aliases=["ctx"], help="Show context injection details for a session")
    p_context.add_argument("session", help="Session ID, path, or agent:id")

    # web
    p_web = subparsers.add_parser("web", help="Start web dashboard")
    p_web.add_argument("--port", "-p", type=int, default=8901, help="Port number")
    p_web.add_argument("--host", default="0.0.0.0", help="Host to bind")
    p_web.add_argument("--debug", action="store_true", help="Debug mode")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    from clawtracerx.cli import (
        cmd_sessions, cmd_analyze, cmd_raw,
        cmd_crons, cmd_subagents, cmd_cost, cmd_context,
    )

    if args.command in ("sessions", "ls"):
        cmd_sessions(agent=args.agent, last_n=args.last, session_type=args.session_type)
    elif args.command in ("analyze", "a"):
        cmd_analyze(session_ref=args.session, no_subagents=args.no_subagents)
    elif args.command == "raw":
        cmd_raw(session_ref=args.session, turn_index=args.turn)
    elif args.command == "crons":
        cmd_crons(last_n=args.last, job=args.job)
    elif args.command in ("subagents", "sub"):
        cmd_subagents(parent=args.parent, last_n=args.last)
    elif args.command == "cost":
        cmd_cost(period=args.period, agent=args.agent)
    elif args.command in ("context", "ctx"):
        cmd_context(session_ref=args.session)
    elif args.command == "web":
        from clawtracerx.web import create_app
        app = create_app()
        print(f"\nClawTracerX web dashboard")
        print(f"http://localhost:{args.port}\n")
        app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
