@AGENTS.md

## Для Claude Code

- Все правила проекта в `AGENTS.md` выше, не дублируй их здесь. Здесь только то, что относится к Claude Code.
- Язык ответов и документов — русский.
- Тесты: `PYTHONPATH=. python3 -m unittest discover -s tests`. Страницу проверяй в браузере: локально `SIM_DB=/путь/sim.db SIM_IDLE_PAUSE=0 python3 -m uvicorn app.main:app --port 8431`, но не запускай прогон на модели без нужды.
- Перед выкладкой на сервер смотри `python3 scripts/simlog.py digest` (см. «Где это крутится» в `AGENTS.md`).
- Коммиты и `git push` только по просьбе владельца. Репозиторий публичный: ключей, паролей и содержимого `data/` в нём быть не должно.
