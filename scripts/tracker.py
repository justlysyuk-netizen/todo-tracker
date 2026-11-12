#!/usr/bin/env python3
"""
Трекер задач: командная строка для data/tasks.json.

Каждая команда меняет data/tasks.json, делает коммит и пушит его,
поэтому страница на GitHub Pages видит изменение почти сразу.
Коммиты складываются в историю разработки.

Примеры:
  python3 scripts/tracker.py add "Палитра сайта" --project potolki --steps "Собрать цвета" "Применить" "Проверить" --start
  python3 scripts/tracker.py step 7 1
  python3 scripts/tracker.py note 7 "подобрал 5 оттенков"
  python3 scripts/tracker.py block 7 "жду фото от Ильи"
  python3 scripts/tracker.py done 7 --note "палитра в style.css"
  python3 scripts/tracker.py list
Флаг --no-push: только записать файл, без коммита и пуша.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_REL = os.path.join("data", "tasks.json")
DATA = os.path.join(ROOT, DATA_REL)
STATUS_RU = {"queue": "Очередь", "in_progress": "В работе", "blocked": "Заблокировано", "done": "Готово"}


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def die(msg):
    print("Ошибка: " + msg, file=sys.stderr)
    sys.exit(1)


# ---------- данные ----------
def load():
    if not os.path.exists(DATA):
        return {"version": 1, "title": "Трекер задач", "updated": now(), "next_id": 1, "tasks": []}
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("tasks", [])
    d["next_id"] = max(d.get("next_id", 1), max((t["id"] for t in d["tasks"]), default=0) + 1)
    return d


def save(d):
    d["updated"] = now()
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    tmp = DATA + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, DATA)


def task(d, tid):
    for t in d["tasks"]:
        if t["id"] == tid:
            return t
    die(f"задачи #{tid} нет")


def log(t, typ, text, by):
    ts = now()
    t.setdefault("log", []).append({"t": ts, "type": typ, "text": text, "by": by})
    t["updated"] = ts


def counts(t):
    s = t.get("steps") or []
    return sum(1 for x in s if x.get("done")), len(s)


def pct(t):
    if t["status"] == "done":
        return 100
    if isinstance(t.get("progress"), (int, float)):
        return int(t["progress"])
    k, n = counts(t)
    return round(k * 100 / n) if n else 0


def begin(t):
    if t["status"] != "in_progress":
        t["status"] = "in_progress"
        t["started"] = t.get("started") or now()
        return True
    return False


# ---------- команды (меняют d, возвращают (сообщение коммита, вывод)) ----------
def c_init(d, a):
    if a.title:
        d["title"] = a.title
    return "⚙ трекер инициализирован", f"Файл {DATA_REL} готов"


def c_add(d, a):
    tid = d["next_id"]
    d["next_id"] += 1
    ts = now()
    t = {
        "id": tid, "title": a.title.strip(), "who": a.who,
        "project": a.project or None, "tags": [x.strip() for x in (a.tags or "").split(",") if x.strip()],
        "status": "queue", "steps": [{"text": s.strip(), "done": False} for s in (a.steps or []) if s.strip()],
        "desc": a.desc or None, "created": ts, "updated": ts, "started": None, "finished": None, "log": [],
    }
    t = {k: v for k, v in t.items() if v is not None or k in ("started", "finished")}
    log(t, "created", "создал(а) задачу", a.by)
    if a.start:
        begin(t)
        log(t, "started", "взял(а) в работу", a.by)
    d["tasks"].append(t)
    return f"[#{tid}] ➕ новая задача: {t['title']}", str(tid)


def c_start(d, a):
    t = task(d, a.id)
    if t["status"] == "done":
        t["finished"] = None
    begin(t)
    log(t, "started", "взял(а) в работу" + (f": {a.note}" if a.note else ""), a.by)
    return f"[#{a.id}] ▶ взял(а) в работу: {t['title']}", f"#{a.id} в работе"


def c_step(d, a):
    t = task(d, a.id)
    s = t.get("steps") or []
    out = []
    for n in a.n:
        if not 1 <= n <= len(s):
            die(f"у задачи #{a.id} шагов {len(s)}, шага {n} нет")
        st = s[n - 1]
        st["done"] = not a.undo
        if a.undo:
            log(t, "step_undone", f"шаг {n} снова открыт: {st['text']}", a.by)
        else:
            log(t, "step", f"шаг {n}/{len(s)} готов: {st['text']}", a.by)
        out.append(n)
    t.pop("progress", None)
    if not a.undo and t["status"] == "queue":
        begin(t)
    if a.note:
        log(t, "note", a.note, a.by)
    k, n = counts(t)
    verb = "снова открыт" if a.undo else "готов"
    return f"[#{a.id}] ☑ шаг {','.join(map(str, out))} {verb} ({k}/{n}): {t['title']}", f"#{a.id}: {k}/{n}, {pct(t)}%"


def c_add_step(d, a):
    t = task(d, a.id)
    for x in a.text:
        t.setdefault("steps", []).append({"text": x, "done": False})
        log(t, "step_added", f"добавлен шаг: {x}", a.by)
    t.pop("progress", None)
    return f"[#{a.id}] ➕ шаги ({len(a.text)}): {t['title']}", f"#{a.id}: шагов {len(t['steps'])}"


def c_progress(d, a):
    t = task(d, a.id)
    if not 0 <= a.pct <= 100:
        die("процент от 0 до 100")
    t["progress"] = a.pct
    if t["status"] == "queue":
        begin(t)
    log(t, "progress", f"прогресс {a.pct}%" + (f": {a.note}" if a.note else ""), a.by)
    return f"[#{a.id}] ⏩ {a.pct}%: {t['title']}", f"#{a.id}: {a.pct}%"


def c_note(d, a):
    t = task(d, a.id)
    log(t, "note", a.text, a.by)
    return f"[#{a.id}] 📝 {a.text}", f"#{a.id}: заметка записана"


def c_block(d, a):
    t = task(d, a.id)
    t["status"] = "blocked"
    log(t, "blocked", f"заблокировано: {a.reason}", a.by)
    return f"[#{a.id}] ⛔ заблокировано: {a.reason}", f"#{a.id} заблокирована"


def c_queue(d, a):
    t = task(d, a.id)
    t["status"] = "queue"
    t["finished"] = None
    log(t, "queued", "вернул(а) в очередь" + (f": {a.note}" if a.note else ""), a.by)
    return f"[#{a.id}] ⏸ в очередь: {t['title']}", f"#{a.id} в очереди"


def c_done(d, a):
    t = task(d, a.id)
    if a.all_steps:
        for s in t.get("steps") or []:
            s["done"] = True
    t["status"] = "done"
    t["started"] = t.get("started") or t["created"]
    t["finished"] = now()
    t.pop("progress", None)
    log(t, "done", "готово" + (f": {a.note}" if a.note else ""), a.by)
    return f"[#{a.id}] ✅ готово: {t['title']}", f"#{a.id} готова"


def c_reopen(d, a):
    t = task(d, a.id)
    t["finished"] = None
    begin(t) if a.start else t.update(status="queue")
    log(t, "reopened", "снова открыта" + (f": {a.note}" if a.note else ""), a.by)
    return f"[#{a.id}] ↺ снова открыта: {t['title']}", f"#{a.id} открыта"


def c_edit(d, a):
    t = task(d, a.id)
    changed = []
    for k in ("title", "who", "project", "desc"):
        v = getattr(a, k)
        if v is not None:
            t[k] = v
            changed.append(k)
    if a.tags is not None:
        t["tags"] = [x.strip() for x in a.tags.split(",") if x.strip()]
        changed.append("tags")
    if not changed:
        die("нечего менять")
    log(t, "edited", "изменено: " + ", ".join(changed), a.by)
    return f"[#{a.id}] ✏ изменено: {', '.join(changed)}", f"#{a.id} обновлена"


def c_delete(d, a):
    task(d, a.id)
    d["tasks"] = [t for t in d["tasks"] if t["id"] != a.id]
    return f"[#{a.id}] 🗑 задача удалена", f"#{a.id} удалена"


def c_list(a):
    d = load()
    ts = d["tasks"] if a.all else [t for t in d["tasks"] if t["status"] != "done" or a.status == "done"]
    if a.status:
        ts = [t for t in ts if t["status"] == a.status]
    if not ts:
        print("Задач нет")
    for t in sorted(ts, key=lambda t: (list(STATUS_RU).index(t["status"]), t["id"])):
        k, n = counts(t)
        print(f"#{t['id']:<4} {STATUS_RU[t['status']]:<14} {pct(t):>3}%  {k}/{n}  {t.get('who','')}  [{t.get('project','')}]  {t['title']}")


def c_show(a):
    t = task(load(), a.id)
    print(json.dumps(t, ensure_ascii=False, indent=2))


# ---------- git ----------
def git(*args, check=False):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, check=check)


def has_remote():
    return git("rev-parse", "--is-inside-work-tree").returncode == 0 and bool(git("remote").stdout.strip())


def pull():
    r = git("pull", "--rebase", "--autostash", "-q")
    if r.returncode != 0:
        git("rebase", "--abort")
        print("Предупреждение: git pull не прошёл: " + (r.stderr.strip() or r.stdout.strip()), file=sys.stderr)


def run(op, a):
    online = not a.no_push and has_remote()
    if online:
        pull()
    for attempt in range(5):
        d = load()
        msg, out = op(d, a)
        save(d)
        if not online:
            print(out)
            return
        git("add", DATA_REL, check=True)
        trailer = os.environ.get("TRACKER_COMMIT_TRAILER", "").strip()
        c = git("commit", "-q", "-m", msg + ("\n\n" + trailer if trailer else ""))
        if c.returncode != 0:
            die("коммит не удался: " + (c.stderr.strip() or c.stdout.strip()))
        p = git("push", "-q")
        if p.returncode == 0:
            print(out)
            return
        # кто-то успел запушить раньше: откатываем свой коммит, подтягиваем и повторяем
        git("reset", "--soft", "HEAD~1")
        git("restore", "--staged", "--worktree", DATA_REL)
        pull()
        time.sleep(1 + attempt)
    die("не удалось запушить после 5 попыток: " + (p.stderr.strip() or p.stdout.strip()))


# ---------- разбор аргументов ----------
def main():
    ap = argparse.ArgumentParser(description="Трекер задач: data/tasks.json + git push")
    ap.add_argument("--no-push", action="store_true", help="не коммитить и не пушить")
    ap.add_argument("--by", default=os.environ.get("TRACKER_BY", "Claude"), help="кто делает запись (по умолчанию Claude)")
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("init"); p.add_argument("--title"); p.set_defaults(f=c_init)
    p = sp.add_parser("add", help="новая задача, печатает её номер")
    p.add_argument("title"); p.add_argument("--who", default="Claude"); p.add_argument("--project")
    p.add_argument("--tags", help="через запятую"); p.add_argument("--steps", nargs="*")
    p.add_argument("--desc"); p.add_argument("--start", action="store_true", help="сразу в работу")
    p.set_defaults(f=c_add)
    p = sp.add_parser("start"); p.add_argument("id", type=int); p.add_argument("--note"); p.set_defaults(f=c_start)
    p = sp.add_parser("step", help="отметить шаг(и) по номеру с 1")
    p.add_argument("id", type=int); p.add_argument("n", type=int, nargs="+"); p.add_argument("--undo", action="store_true")
    p.add_argument("--note"); p.set_defaults(f=c_step)
    p = sp.add_parser("add-step"); p.add_argument("id", type=int); p.add_argument("text", nargs="+"); p.set_defaults(f=c_add_step)
    p = sp.add_parser("progress"); p.add_argument("id", type=int); p.add_argument("pct", type=int); p.add_argument("--note"); p.set_defaults(f=c_progress)
    p = sp.add_parser("note"); p.add_argument("id", type=int); p.add_argument("text"); p.set_defaults(f=c_note)
    p = sp.add_parser("block"); p.add_argument("id", type=int); p.add_argument("reason"); p.set_defaults(f=c_block)
    p = sp.add_parser("queue"); p.add_argument("id", type=int); p.add_argument("--note"); p.set_defaults(f=c_queue)
    p = sp.add_parser("done"); p.add_argument("id", type=int); p.add_argument("--note")
    p.add_argument("--all-steps", action="store_true", help="отметить все шаги выполненными"); p.set_defaults(f=c_done)
    p = sp.add_parser("reopen"); p.add_argument("id", type=int); p.add_argument("--note"); p.add_argument("--start", action="store_true"); p.set_defaults(f=c_reopen)
    p = sp.add_parser("edit"); p.add_argument("id", type=int)
    for k in ("--title", "--who", "--project", "--tags", "--desc"):
        p.add_argument(k)
    p.set_defaults(f=c_edit)
    p = sp.add_parser("delete"); p.add_argument("id", type=int); p.set_defaults(f=c_delete)
    p = sp.add_parser("list"); p.add_argument("--all", action="store_true"); p.add_argument("--status", choices=list(STATUS_RU)); p.set_defaults(ro=c_list)
    p = sp.add_parser("show"); p.add_argument("id", type=int); p.set_defaults(ro=c_show)

    a = ap.parse_args()
    if getattr(a, "ro", None):
        if not a.no_push and has_remote():
            pull()
        return a.ro(a)
    run(a.f, a)


if __name__ == "__main__":
    main()
