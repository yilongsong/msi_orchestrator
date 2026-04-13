import curses
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "experiments.json")
STATUS_OPTIONS = ["active", "pending", "inactive", "finished"]
OWNER_OPTIONS = ["song0837", "chand863"]

def get_block_bounds(items, idx):
    if isinstance(items[idx][1], str) and "TASKS" in items[idx][1]:
        start = idx
        end = idx
        while end + 1 < len(items):
            nxt = items[end + 1]
            if isinstance(nxt[1], str) and "TASKS" in nxt[1]: break
            if isinstance(nxt[1], bool): break
            end += 1
        return start, end
    elif isinstance(items[idx][1], str) and "series" in items[idx][1]:
        start = idx
        end = idx
        while end + 1 < len(items) and isinstance(items[end + 1][1], dict):
            end += 1
        return start, end
    else:
        return idx, idx

def main(stdscr):
    curses.curs_set(0) # Hide cursor
    stdscr.nodelay(False) # Blocking getch
    
    # Setup colors using default terminal backgrounds so it looks native
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN) # Selected block
    curses.init_pair(2, curses.COLOR_GREEN, -1)  # Active
    curses.init_pair(3, curses.COLOR_YELLOW, -1) # Pending
    curses.init_pair(4, curses.COLOR_RED, -1)    # Inactive
    curses.init_pair(5, curses.COLOR_BLUE, -1)   # Finished

    try:
        with open(CONFIG_FILE, 'r') as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        stdscr.addstr(0, 0, f"Error: {CONFIG_FILE} not found. Press any key to exit.")
        stdscr.getch()
        return

    # Convert the dictionary to a strict ordered list of tuples natively preserving JSON struct
    items = list(raw_data.items())
    
    selected_idx = 0
    top_line = 0

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        # Header graphics
        header = " EXPERIMENT MANAGER TUI ".center(w, "=")
        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(0, 0, header[:w])
        stdscr.attroff(curses.A_BOLD)
        
        info = " [UP/DOWN] Nav | [SPACE] Status | [O] Owner | [W/S] Move | [N] Restart | [ENTER] Save "
        stdscr.addstr(1, 0, info.center(w)[:w])
        stdscr.addstr(2, 0, "-" * w)

        max_display = h - 5
        
        # Smooth camera tracking / pagination
        if selected_idx < top_line:
            top_line = selected_idx
        elif selected_idx >= top_line + max_display:
            top_line = selected_idx - max_display + 1

        for i in range(max_display):
            item_idx = top_line + i
            if item_idx >= len(items):
                break
            
            k, v = items[item_idx]
            
            # Identify row rendering pattern based on Object type (Configs vs Comments vs Bools)
            if isinstance(v, dict):
                st = v.get('status', 'inactive')
                owner = v.get('owner', 'None')
                target = v.get('target', 500)
                display_str = f" [{st.upper():^8}] {k:<25} (Owner: {owner:<10} | Target: {target})"
                
                # Semantic coloring
                color = curses.color_pair(0)
                if st == 'active': color = curses.color_pair(2)
                elif st == 'pending': color = curses.color_pair(3)
                elif st == 'inactive': color = curses.color_pair(4)
                elif st == 'finished': color = curses.color_pair(5)
            elif isinstance(v, bool):
                display_str = f" [{str(v).upper():^8}] {k:<25} (Global Flag)"
                color = curses.color_pair(2) if v else curses.color_pair(4)
            else:
                display_str = f" >>> {v} <<< "
                color = curses.color_pair(0)
                
            display_str = display_str[:w-2]

            # Render logic
            if item_idx == selected_idx:
                stdscr.attron(curses.color_pair(1))
                stdscr.addstr(i + 4, 1, display_str.ljust(w-2))
                stdscr.attroff(curses.color_pair(1))
            else:
                stdscr.attron(color)
                stdscr.addstr(i + 4, 1, display_str.ljust(w-2))
                stdscr.attroff(color)

        # Footer graphics
        footer_str = f" Target: {CONFIG_FILE} | Selection: {selected_idx+1}/{len(items)} "
        try:
            stdscr.addstr(h-1, 0, footer_str.center(w-1)[:w-1], curses.A_REVERSE)
        except curses.error:
            pass
        
        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_UP:
            selected_idx = max(0, selected_idx - 1)
        elif key == curses.KEY_DOWN:
            selected_idx = min(len(items) - 1, selected_idx + 1)
        elif key == ord(' '):
            k, v = items[selected_idx]
            if isinstance(v, dict):
                cur_st = v.get('status', 'inactive')
                if cur_st in STATUS_OPTIONS:
                    next_idx = (STATUS_OPTIONS.index(cur_st) + 1) % len(STATUS_OPTIONS)
                    v['status'] = STATUS_OPTIONS[next_idx]
                else:
                    v['status'] = 'active'
            elif isinstance(v, bool):
                items[selected_idx] = (k, not v)
        elif key in [ord('o'), ord('O')]:
            k, v = items[selected_idx]
            if isinstance(v, dict):
                cur_owner = v.get('owner', 'song0837')
                if cur_owner in OWNER_OPTIONS:
                    next_idx = (OWNER_OPTIONS.index(cur_owner) + 1) % len(OWNER_OPTIONS)
                    v['owner'] = OWNER_OPTIONS[next_idx]
                else:
                    v['owner'] = OWNER_OPTIONS[0]
        elif key in [ord('n'), ord('N')]:
            k, v = items[selected_idx]
            if isinstance(v, dict):
                v['job_id'] = None
                # Set status to active so orchestrator picks it up
                v['status'] = 'active'
        elif key in [ord('w'), ord('W')]:
            if isinstance(items[selected_idx][1], str) and ("TASKS" in items[selected_idx][1] or "series" in items[selected_idx][1]):
                drag_start, drag_end = get_block_bounds(items, selected_idx)
                if drag_start > 0:
                    prev_start = drag_start - 1
                    if isinstance(items[prev_start][1], dict):
                        while prev_start > 0 and isinstance(items[prev_start - 1][1], dict):
                            prev_start -= 1
                        if prev_start > 0 and isinstance(items[prev_start - 1][1], str) and "series" in items[prev_start - 1][1]:
                            prev_start -= 1
                    if "TASKS" in str(items[drag_start][1]):
                        while prev_start > 0:
                            if isinstance(items[prev_start - 1][1], str) and "TASKS" in str(items[prev_start - 1][1]):
                                prev_start -= 1
                                break
                            if isinstance(items[prev_start - 1][1], bool): break
                            prev_start -= 1
                    items[prev_start : drag_end + 1] = items[drag_start : drag_end + 1] + items[prev_start : drag_start]
                    selected_idx = prev_start
            else:
                if selected_idx > 0:
                    items[selected_idx], items[selected_idx-1] = items[selected_idx-1], items[selected_idx]
                    selected_idx -= 1
                    
        elif key in [ord('s'), ord('S')]:
            if isinstance(items[selected_idx][1], str) and ("TASKS" in items[selected_idx][1] or "series" in items[selected_idx][1]):
                drag_start, drag_end = get_block_bounds(items, selected_idx)
                if drag_end < len(items) - 1:
                    over_start, over_end = get_block_bounds(items, drag_end + 1)
                    items[drag_start : over_end + 1] = items[over_start : over_end + 1] + items[drag_start : drag_end + 1]
                    selected_idx = drag_start + (over_end - over_start + 1)
            else:
                if selected_idx < len(items) - 1:
                    items[selected_idx], items[selected_idx+1] = items[selected_idx+1], items[selected_idx]
                    selected_idx += 1
        elif key in [ord('q'), ord('Q'), 10, 13]:
            break

    # Commit phase
    stdscr.erase()
    stdscr.addstr(0, 0, "Saving ordered state machine back to experiments.json... ")
    stdscr.refresh()

    new_dict = {}
    for k, v in items:
        new_dict[k] = v

    with open(CONFIG_FILE, 'w') as f:
        json.dump(new_dict, f, indent=2)

if __name__ == "__main__":
    os.environ.setdefault('ESCDELAY', '25')
    curses.wrapper(main)
