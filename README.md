# Log Explorer TUI

**Log Explorer** is a terminal-based log analysis tool designed for clarity, flexibility, and modular extensibility.  
It supports a variety of log formats (structured and unstructured), search functionality, statistics, and visualizations — all through a powerful TUI (Text User Interface).

---

---

## Installation

### Requirements

- Python 3.7+
- `pip`

### 1. Clone the repository and install using pip

```bash
git clone https://github.com/MS-32154/py-log-analyzer

cd py-log-analyzer

pip install .
```

### 2. Launch the application

```bash
log_explorer
```

---

## Workflow Overview

1. **FILES TAB** – Navigate and select a log file
2. **Process (`p`)** – Analyze the log structure with the inference engine
3. **SEARCH TAB** – Filter log entries based on structured and raw fields
4. **STATS TAB** – Review aggregated metrics and field distributions
5. **PLOTS TAB** – Visual visualizations like time histograms and frequency charts

---

## Global Controls

| Key            | Action             |
| -------------- | ------------------ |
| `Tab`          | Switch to next tab |
| `q`            | Quit application   |
| `Page Up/Down` | Scroll tab content |

---

## Files Tab

| Key       | Action                                 |
| --------- | -------------------------------------- |
| `Up/Down` | Navigate files and directories         |
| `Enter`   | Enter a directory / Load selected file |
| `c`       | Change directory (input mode)          |
| `r`       | Refresh file list                      |
| `p`       | Process and analyze selected log file  |

---

## Search Tab

### Navigation Mode

| Key            | Action                           |
| -------------- | -------------------------------- |
| `Shift+Tab`    | Move between form fields         |
| `Up/Down`      | Navigate between fields          |
| `Enter`/`Type` | Edit a field                     |
| `Space`        | Toggle operator or boolean value |
| `Backspace`    | Clear field                      |
| `Enter`        | Execute search                   |

### Input Mode

| Key      | Action                   |
| -------- | ------------------------ |
| `Type`   | Edit input field         |
| `Enter`  | Save and exit input mode |
| `Esc`    | Cancel and exit input    |
| `Ctrl+U` | Clear current input line |

### Search Results

| Key            | Action                        |
| -------------- | ----------------------------- |
| `v`            | Toggle raw log lines          |
| `Page Up/Down` | Scroll through search results |
| `F/B`          | Scroll field value table      |

### Time Format

Use the standard for search filters:

`YYYY-MM-DD HH:MM:SS`

---

## Future Improvements

- Smarter detection engine — machine learning models for log inference

- Multi-file mode in TUI — backend support exists; UI coming soon

- Library interface — allow the engines to be used as an importable Python library

- TUI enhancements — better layout, filters, search UX, and tab interactions

---

## Contributing

Contributions are welcome and encouraged!
Please fork the repository and submit a pull request, or open an issue to discuss your ideas or report bugs.

---

## 📖 Background

This project was created for the Boot.dev Hackathon.
Originally, the idea was to rewrite my first project, [py-json-analyzer](https://github.com/MS-32154/py-json-analyzer), in Go — but ultimately decided to stick with Python because I'm still gaining flexibility with Go and was short on time.

So I built this tool in Python instead, focusing on log files rather than just JSON. I wrote the core engines myself, but AI helped significantly with regex pattern generation, debugging, and improving the code — especially for the TUI, which was largely AI-generated.

While regex isn't the best tool for everything, this project aims for modularity and extensibility — with plans for smarter parsing in the future.

---

## 📝 License

MIT License © [MS-32154](https://github.com/MS-32154)

---
