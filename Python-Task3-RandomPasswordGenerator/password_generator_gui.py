import secrets
import string
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import pyperclip
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

MIN_LENGTH = 8
MAX_LENGTH = 64
HISTORY_LIMIT = 5

# Characters that are easy to visually confuse with one another
AMBIGUOUS_CHARS = "0Ol1I|`'\""


class PasswordGeneratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Random Password Generator")
        self.root.resizable(False, False)

        # Session-only history (in memory, never saved to disk)
        self.history = []

        self._build_widgets()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_widgets(self):
        pad = {"padx": 12, "pady": 6}

        main = ttk.Frame(self.root)
        main.grid(row=0, column=0, sticky="nsew", **pad)

        # --- Length control -------------------------------------------------
        ttk.Label(main, text="Password Length", font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )

        self.length_var = tk.IntVar(value=16)
        self.length_label_var = tk.StringVar(value="16")

        length_frame = ttk.Frame(main)
        length_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        self.length_scale = ttk.Scale(
            length_frame,
            from_=MIN_LENGTH,
            to=MAX_LENGTH,
            orient="horizontal",
            variable=self.length_var,
            command=self._on_length_change,
            length=220,
        )
        self.length_scale.pack(side="left")
        ttk.Label(length_frame, textvariable=self.length_label_var, width=4).pack(
            side="left", padx=(8, 0)
        )

        # --- Character type checkboxes --------------------------------------
        ttk.Label(main, text="Character Types", font=("Segoe UI", 10, "bold")).grid(
            row=2, column=0, columnspan=2, sticky="w"
        )

        self.use_upper = tk.BooleanVar(value=True)
        self.use_lower = tk.BooleanVar(value=True)
        self.use_digits = tk.BooleanVar(value=True)
        self.use_symbols = tk.BooleanVar(value=False)
        self.exclude_ambiguous = tk.BooleanVar(value=False)

        ttk.Checkbutton(main, text="Uppercase (A-Z)", variable=self.use_upper).grid(
            row=3, column=0, sticky="w"
        )
        ttk.Checkbutton(main, text="Lowercase (a-z)", variable=self.use_lower).grid(
            row=3, column=1, sticky="w"
        )
        ttk.Checkbutton(main, text="Numbers (0-9)", variable=self.use_digits).grid(
            row=4, column=0, sticky="w"
        )
        ttk.Checkbutton(main, text="Symbols (!@#...)", variable=self.use_symbols).grid(
            row=4, column=1, sticky="w"
        )
        ttk.Checkbutton(
            main,
            text="Exclude ambiguous characters (0, O, l, 1, I ...)",
            variable=self.exclude_ambiguous,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 8))

        # --- Generate button --------------------------------------------------
        self.generate_btn = ttk.Button(
            main, text="Generate Password", command=self.on_generate
        )
        self.generate_btn.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        # --- Result display -----------------------------------------------
        ttk.Label(main, text="Generated Password", font=("Segoe UI", 10, "bold")).grid(
            row=7, column=0, columnspan=2, sticky="w"
        )

        result_frame = ttk.Frame(main)
        result_frame.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        self.password_var = tk.StringVar(value="")
        self.password_entry = ttk.Entry(
            result_frame, textvariable=self.password_var, font=("Consolas", 12), width=28
        )
        self.password_entry.pack(side="left", fill="x", expand=True)

        self.copy_btn = ttk.Button(
            result_frame, text="Copy to Clipboard", command=self.on_copy
        )
        self.copy_btn.pack(side="left", padx=(8, 0))

        # --- Strength indicator ---------------------------------------------
        ttk.Label(main, text="Strength", font=("Segoe UI", 10, "bold")).grid(
            row=9, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        self.strength_bar = ttk.Progressbar(
            main, orient="horizontal", length=280, mode="determinate", maximum=100
        )
        self.strength_bar.grid(row=10, column=0, columnspan=2, sticky="ew")

        self.strength_label_var = tk.StringVar(value="—")
        self.strength_label = ttk.Label(main, textvariable=self.strength_label_var)
        self.strength_label.grid(row=11, column=0, columnspan=2, sticky="w", pady=(2, 8))

        # --- History ------------------------------------------------------
        ttk.Label(
            main, text="History (last 5, this session only)", font=("Segoe UI", 10, "bold")
        ).grid(row=12, column=0, columnspan=2, sticky="w")

        self.history_list = tk.Listbox(main, height=5, width=38, font=("Consolas", 10))
        self.history_list.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(4, 0))

        if not CLIPBOARD_AVAILABLE:
            ttk.Label(
                main,
                text="Note: pyperclip not installed — clipboard copy disabled.\n"
                "Run: pip install pyperclip",
                foreground="#b00020",
            ).grid(row=14, column=0, columnspan=2, sticky="w", pady=(8, 0))

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def _on_length_change(self, _event=None):
        self.length_label_var.set(str(int(float(self.length_var.get()))))

    def _selected_pools(self):
        """Return list of (pool_string) for each checked character type."""
        pools = []
        if self.use_upper.get():
            pools.append(string.ascii_uppercase)
        if self.use_lower.get():
            pools.append(string.ascii_lowercase)
        if self.use_digits.get():
            pools.append(string.digits)
        if self.use_symbols.get():
            pools.append(string.punctuation)
        return pools

    def _strip_ambiguous(self, pool):
        if self.exclude_ambiguous.get():
            return "".join(c for c in pool if c not in AMBIGUOUS_CHARS)
        return pool

    def on_generate(self):
        length = int(float(self.length_var.get()))

        if length < MIN_LENGTH:
            messagebox.showerror(
                "Invalid length", f"Password length must be at least {MIN_LENGTH}."
            )
            return

        pools = self._selected_pools()
        if len(pools) < 2:
            messagebox.showerror(
                "Selection required",
                "Please select at least 2 character types.",
            )
            return

        # Apply ambiguous-character exclusion per pool, guard against
        # a pool becoming empty (e.g. digits-only with exclusion on).
        cleaned_pools = []
        for pool in pools:
            cleaned = self._strip_ambiguous(pool)
            if not cleaned:
                messagebox.showerror(
                    "No characters available",
                    "Excluding ambiguous characters left one of the selected "
                    "types with no usable characters. Deselect 'Exclude "
                    "ambiguous characters' or choose different types.",
                )
                return
            cleaned_pools.append(cleaned)

        password = self._generate_secure_password(length, cleaned_pools)
        self.password_var.set(password)

        self._update_strength(password, cleaned_pools)
        self._add_to_history(password)

        if CLIPBOARD_AVAILABLE:
            try:
                pyperclip.copy(password)
            except Exception:
                # Clipboard access can fail in headless/sandboxed environments;
                # generation itself should still succeed.
                pass

    def on_copy(self):
        password = self.password_var.get()
        if not password:
            messagebox.showinfo("Nothing to copy", "Generate a password first.")
            return
        if not CLIPBOARD_AVAILABLE:
            messagebox.showerror(
                "Clipboard unavailable", "Install pyperclip: pip install pyperclip"
            )
            return
        try:
            pyperclip.copy(password)
        except Exception as exc:
            messagebox.showerror("Copy failed", str(exc))

    # ------------------------------------------------------------------
    # Core generation logic
    # ------------------------------------------------------------------
    def _generate_secure_password(self, length, pools):
        """Cryptographically secure generation guaranteeing at least one
        character from each selected pool."""
        all_chars = "".join(pools)

        # Guarantee representation of every selected type
        password_chars = [secrets.choice(pool) for pool in pools]

        remaining = length - len(password_chars)
        password_chars += [secrets.choice(all_chars) for _ in range(remaining)]

        # Cryptographically shuffle using secrets-backed random swaps
        # (Fisher-Yates using secrets.randbelow for security)
        for i in range(len(password_chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            password_chars[i], password_chars[j] = password_chars[j], password_chars[i]

        return "".join(password_chars)

    def _update_strength(self, password, pools):
        length = len(password)
        diversity = len(pools)  # number of distinct character types used

        # Simple scoring: length contributes up to 60, diversity up to 40
        length_score = min(length / MAX_LENGTH, 1.0) * 60
        diversity_score = (diversity / 4) * 40
        score = length_score + diversity_score

        if score < 45:
            label, color = "Weak", "#c0392b"
        elif score < 75:
            label, color = "Medium", "#e67e22"
        else:
            label, color = "Strong", "#27ae60"

        self.strength_bar["value"] = score
        self.strength_label_var.set(f"{label}  ({int(score)}/100)")
        self.strength_label.configure(foreground=color)

    def _add_to_history(self, password):
        self.history.insert(0, password)
        self.history = self.history[:HISTORY_LIMIT]

        self.history_list.delete(0, tk.END)
        for pw in self.history:
            self.history_list.insert(tk.END, pw)


def main():
    root = tk.Tk()
    app = PasswordGeneratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
