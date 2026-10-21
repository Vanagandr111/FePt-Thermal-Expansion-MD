# agent.md — FePt Thermal Expansion GUI

Точка входа для ИИ-агентов и людей. Обновляй вместе с кодом.

## Что это

Настольный (локальный веб-) расчётник физики: **тепловое расширение
сплава FePt** методом молекулярной динамики. Два движка:

- **MACE** (нейропотенциал, `mace` mode) — GPU/CUDA, `torch.compile`,
  быстрый; основной.
- **LAMMPS** (`lammps` mode) — классический EAM/MEAM, CPU.

Протокол: для каждой температуры и композиции — релаксация + NPT-MD,
на выходе a(T), тепловой коэффициент α = Δa/(a·ΔT), параметр
Кюри-Вейсса (вкладка Результаты). Интерфейс — локальный веб-GUI,
агенты управляют им через HTTP API и MCP так же, как человек через
браузер (все действия видны в консоли GUI с метками `[agent]`/`[UI]`).

## Стек и структура

```
gui/
  server.py        HTTP-сервер (stdlib), все /api/* роуты, порт 8321
  mcp_server.py    MCP stdio-сервер (JSON-RPC), тонкий мост к /api/*
  estimator.py     расчёт оценки времени/памяти (чистый, тестится)
  sysmetrics.py    CPU/RAM/VRAM/GPU-снимок (stdlib + nvidia-smi)
  elements.py      реестр элементов (валидация/upsert/удаление)
  potfile.py       санитайз имён + атомарная запись потенциалов
  static/index.html  SPA: вкладки Расчёт / Результаты / Зависимости
scripts/
  run_main_mace.py движок MACE-MD (CLI, запускается из GUI)
  calibrate_profile.py  калибровка оценщика на текущей машине
  lmpdata.py       парсер .lmp data-файлов (общий для MD и GUI)
  lmp_helper.py    генерация структур, LAMMPS-обвязка
  gen_structure.py fcc-суперячейка (4·n³ атомов на grid n)
tests/             pytest (81 тест; см. «Тесты»)
potentials/gpu/    MACE .model/.pt  |  potentials/cpu/  EAM/MEAM
data/              elements.json, *.lmp, estim_profile.json (калибровка)
```

Python-окружение: `.venv-mace/Scripts/python.exe` (все команды ниже — из
корня проекта).

## Запуск

```bash
./.venv-mace/Scripts/python.exe gui/server.py      # GUI на 127.0.0.1:8321
./.venv-mace/Scripts/python.exe -m pytest -q       # тесты (81)
./.venv-mace/Scripts/python.exe -u scripts/calibrate_profile.py \
    --device cuda --grids 2 3 4                    # калибровка оценки (~4 мин)
```

Переменные: `FEPT_PORT` (порт), `FEPT_PROJECT_DIR` (корень, нужен в
frozen-сборке). **Не убивай работающий расчёт** — сначала `POST /api/stop`.

## HTTP API (127.0.0.1:8321)

| Роут | Метод | Что |
|---|---|---|
| `/api/form` | GET/POST | форма: mode, model, device, comp, grid, temps, eq, prod, seed, elem_a, elem_b. POST `{"form":{...}}` меняет поля (видно в GUI, метка source) |
| `/api/run` | POST | старт расчёта (ключи — как форма, опциональны). Ошибка, если уже идёт |
| `/api/stop` | POST | остановка активного расчёта |
| `/api/log` | GET | хвост консоли (`?last=40`) |
| `/api/log/stream` | GET | SSE-поток консоли |
| `/api/results` | GET | разобранные a(T) и CTE (`?outdir=`) |
| `/api/structure` | GET | newest `.lmp`: позиции/ячейка/счётчики/x_Pt (`?outdir=`) |
| `/api/estimate` | GET | оценка времени/памяти по текущей форме |
| `/api/estimate` | POST | то же, `{"form":{...}}` — ответ на «а если grid=8?» БЕЗ изменения формы |
| `/api/metrics` | GET | CPU/RAM/VRAM/GPU + уровни ok/warn/bad |
| `/api/deps` | GET | проверка зависимостей (`?refresh=1`) |
| `/api/potentials` | GET | индекс потенциалов gpu/cpu |
| `/api/potentials/upload` | POST | браузерная загрузка (raw body, `?name=`) |
| `/api/potentials/copy` | POST | импорт локального файла `{"path":...}` (для агентов) |
| `/api/elements` | GET | реестр элементов |
| `/api/elements` | POST | `{"action":"save","item":{symbol,lc,label}}` / `{"action":"delete","symbol":...}` |
| `/api/elements/compat` | GET | совместимость элементов с потенциалом |
| `/api/download_lammps` /`_model` | POST | скачать LAMMPS/модель MACE (долгое) |
| `/api/download_status` | GET | прогресс загрузок/установок (ползунок в GUI) |
| `/api/install_lib` | POST | `{"name":...}` pip-установка в интерпретатор движка |
| `/api/calibrate` | POST | калибровка оценщика (~4 мин, лог в консоль) |
| `/api/open_folder` | POST | открыть папку в проводнике (`{"path":...}`) |

Ошибки: JSON `{"ok": false, "error": "..."}`; коды HTTP — 200.

## MCP (управление GUI из агента)

20 тулов (`gui_status`, `gui_get_form`, `gui_set_form`, `gui_list_potentials`,
`gui_check_dependencies`, `gui_start_run`, `gui_stop_run`, `gui_read_log`,
`gui_get_results`, `gui_open_results_folder`, `gui_download_lammps`,
`gui_download_model`, `gui_metrics`, `gui_estimate`, `gui_calibrate`,
`gui_structure`, `gui_add_potential`, `gui_get_elements`,
`gui_save_element`, `gui_delete_element`).

Регистрация в `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  fept_gui:
    command: C:/Users/<user>/AppData/Local/Python/pythoncore-3.14-64/python.exe
    args: ["D:/projects/<repo>/gui/mcp_server.py"]
    env: {FEPT_GUI_URL: "http://127.0.0.1:8321"}
    enabled: true
```

Сервер MCP должен быть поднят (`gui/server.py`) — все тулы отвечают
понятной ошибкой, если нет. После правок mcp_server.py нужна
перерегистрация (`/reload-mcp` в Hermes). Схема проверяется тестом
`tests/test_mcp_registry.py`: каждый тул обязан иметь dispatch-ветку и
наоборот.

Типовой сценарий агента:
```
gui_status → gui_set_form(grid=4, temps="300 1200") → gui_estimate
→ gui_start_run → gui_read_log → gui_get_results → gui_structure
```

## CLI движка (без GUI)

```bash
./.venv-mace/Scripts/python.exe -u scripts/run_main_mace.py \
    --device cuda --model potentials/gpu/<mace>.model \
    --comps 0.5 --temps 300 1200 --grid 4 --seed 42 --out results_xxx
./.venv-mace/Scripts/python.exe -u scripts/calibrate_profile.py \
    --device cuda --grids 2 3 4 [--single 4] [--model path]
```

`grid n` → `4·n³` атомов (2→32, 3→108, 4→256, 8→2048).

## Тесты и конвенции (TDD)

- Запуск: `./.venv-mace/Scripts/python.exe -m pytest -q`.
- Покрыты: estimator (формулы/интерполяция), sysmetrics, lmpdata
  (парсер), elements, potfile, gui_state, mcp_registry, engine_python,
  browser_open.
- Правило: сначала тест на чистую функцию, потом реализация. Логика,
  зависящая от железа/процессов, выносится в чистые функции с порогами
  (см. `estimator.fits_memory`, `sysmetrics.level`).
- Новый MCP-тул = запись в `TOOLS` + ветка в `call_tool` (иначе тест
  `test_no_stray_dispatch_branches` упадёт).

## Данные и воспроизводимость

- `data/estim_profile.json` — калибровка оценщика ПОД КОНКРЕТНУЮ машину
  (не коммитить, в `.gitignore`); авто-обновляется из каждого
  завершённого расчёта (строка `ms/step=...` в логе).
- `seed` — воспроизводимость NPT-инициализации; одинаковый seed → одна
  и траектория.
- Структура читается из `.lmp` через `scripts/lmpdata.py` — единственный
  источник формата для MD и GUI.
- Профиль оценки честно маркирует достоверность: `calibrated` /
  `extrapolated` / `guess` — не выдавай `guess` за измерение.
