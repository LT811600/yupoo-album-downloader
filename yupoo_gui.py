"""Yupoo album downloader for Windows."""
import os
import sys
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from tkinter import filedialog, messagebox, ttk

from yupoo_gui_download import album_address, download, find_albums

BG, WHITE, INK, BLUE = '#eef3fb', '#ffffff', '#122241', '#204cdb'
FONT = 'Microsoft YaHei UI'


class App:
    def __init__(self, root):
        self.root = root
        root.title('Yupoo 相册下载器')
        root.geometry('780x730')
        root.minsize(630, 590)
        root.configure(bg=BG)
        root.option_add('*Font', (FONT, 10))
        self.events = Queue()
        self.busy = False
        self.albums = []
        self.checked = set()
        self.source = None
        self.errors = []
        self.last_folder = None
        self.address = tk.StringVar()
        self.keywords = tk.StringVar()
        default = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
        self.folder = tk.StringVar(value=str(default / 'Yupoo下载'))
        self.mode = tk.StringVar(value='width')
        self.width = tk.StringVar(value='800')
        self.status = tk.StringVar(value='等待获取相册')
        self.count = tk.StringVar(value='已选 0 / 0')

        outer = tk.Frame(root, bg=BG, padx=20, pady=14)
        outer.pack(fill='both', expand=True)
        self.label(outer, 'Yupoo 相册下载器', size=23, bold=True, bg=BG).pack(anchor='w')
        self.label(outer, '按关键词筛选相册，批量保存图片', bg=BG).pack(anchor='w', pady=(0, 12))
        settings = self.panel(outer)
        settings.columnconfigure(1, weight=1)
        for row, title, value in ((0, '相册地址', self.address), (1, '相册关键词', self.keywords),
                                  (3, '保存目录', self.folder)):
            self.label(settings, title, bold=True).grid(row=row, column=0, sticky='w', padx=(0, 13), pady=4)
            entry = ttk.Entry(settings, textvariable=value)
            entry.grid(row=row, column=1, columnspan=1 if row == 3 else 2, sticky='ew', pady=4, ipady=3)
            if row == 0:
                entry.focus_set()
        hint = '多个关键词用逗号分隔，匹配任意一个即可。留空代表相册地址包含的全部相册。'
        self.label(settings, hint, size=9, wraplength=470).grid(row=2, column=1, columnspan=2, sticky='w')
        ttk.Button(settings, text='选择文件夹', command=self.choose_folder).grid(row=3, column=2, padx=(8, 0))
        self.label(settings, '图片尺寸', bold=True).grid(row=4, column=0, sticky='w', pady=5)
        sizes = tk.Frame(settings, bg=WHITE)
        sizes.grid(row=4, column=1, columnspan=2, sticky='w')
        for name, value in (('原图', 'original'), ('宽度等于或大于', 'width')):
            tk.Radiobutton(sizes, text=name, value=value, variable=self.mode, bg=WHITE,
                           activebackground=WHITE, command=self.sync_width).pack(side='left', padx=(0, 8))
        self.width_field = ttk.Spinbox(sizes, from_=1, to=99999, width=7, textvariable=self.width)
        self.width_field.pack(side='left', padx=(0, 6))
        self.label(sizes, '像素').pack(side='left')
        self.label(settings, '宽度小于设定值的图片将跳过。', size=9).grid(row=5, column=1, columnspan=2, sticky='w')
        self.get_button = self.primary(settings, '获取相册', self.get_albums)
        self.get_button.grid(row=6, column=0, columnspan=3, pady=(9, 0), ipadx=30)

        selection = self.panel(outer, expand=True)
        self.label(selection, '勾选相册', 15, True).pack(anchor='w')
        bar = tk.Frame(selection, bg=WHITE)
        bar.pack(fill='x', pady=6)
        ttk.Button(bar, text='全选', command=lambda: self.select_all(True)).pack(side='left')
        ttk.Button(bar, text='取消全选', command=lambda: self.select_all(False)).pack(side='left', padx=7)
        ttk.Label(bar, textvariable=self.count, background=WHITE).pack(side='left', padx=8)
        listing = tk.Frame(selection, bg=WHITE)
        listing.pack(fill='both', expand=True)
        self.table = ttk.Treeview(listing, columns=('album',), show='tree', height=4, selectmode='browse')
        self.table.column('#0', width=630, minwidth=390)
        scroll = ttk.Scrollbar(listing, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.table.pack(side='left', fill='both', expand=True)
        self.table.bind('<Button-1>', lambda event: self.toggle(self.table.identify_row(event.y)))
        self.table.bind('<space>', lambda event: self.toggle(self.table.focus()))

        progress = self.panel(outer)
        self.label(progress, '下载进度', 15, True).pack(anchor='w')
        status_line = tk.Frame(progress, bg=WHITE)
        status_line.pack(fill='x', pady=(3, 5))
        ttk.Label(status_line, textvariable=self.status, background=WHITE, wraplength=470).pack(side='left', fill='x', expand=True)
        ttk.Button(status_line, text='打开保存目录', command=self.open_folder).pack(side='right', padx=(5, 0))
        self.progress = ttk.Progressbar(progress, maximum=100)
        self.progress.pack(fill='x')
        self.start = self.primary(outer, '开始下载', self.start_download)
        self.start.pack(fill='x', pady=(3, 0))
        self.start.configure(state='disabled')
        for field in (self.address, self.keywords):
            field.trace_add('write', lambda *_: self.update_selection())
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(60, self.handle_events)

    @staticmethod
    def label(parent, text, size=10, bold=False, bg=WHITE, **options):
        return tk.Label(parent, text=text, font=(FONT, size, 'bold' if bold else 'normal'),
                        bg=bg, fg=INK, justify='left', **options)

    @staticmethod
    def panel(parent, expand=False):
        panel = tk.Frame(parent, bg=WHITE, highlightthickness=1, highlightbackground='#c9d5e8', padx=13, pady=9)
        panel.pack(fill='both' if expand else 'x', expand=expand, pady=(0, 9))
        return panel

    @staticmethod
    def primary(parent, title, command):
        return tk.Button(parent, text=title, command=command, bg=BLUE, fg=WHITE, activebackground='#163cba',
                         activeforeground=WHITE, disabledforeground='#cfd9ff', relief='flat',
                         pady=6, font=(FONT, 12, 'bold'))

    def sync_width(self):
        self.width_field.configure(state='normal' if self.mode.get() == 'width' else 'disabled')

    def choose_folder(self):
        path = filedialog.askdirectory(parent=self.root)
        if path:
            self.folder.set(path)

    def open_folder(self):
        folder = self.last_folder or Path(self.folder.get().strip())
        if folder.is_dir():
            os.startfile(folder)
        else:
            messagebox.showinfo('保存目录', '下载后可打开保存目录。', parent=self.root)

    def selection_key(self):
        return self.address.get().strip(), self.keywords.get().strip()

    def update_selection(self):
        self.count.set(f'已选 {len(self.checked)} / {len(self.albums)}')
        enabled = bool(self.checked) and not self.busy and self.source == self.selection_key()
        self.start.configure(state='normal' if enabled else 'disabled')

    def row_text(self, index):
        return ('☑   ' if index in self.checked else '☐   ') + self.albums[index][0]

    def toggle(self, row):
        if row and not self.busy:
            index = int(row)
            self.checked.symmetric_difference_update({index})
            self.table.item(row, text=self.row_text(index))
            self.update_selection()

    def select_all(self, selected):
        if not self.busy:
            self.checked = set(range(len(self.albums))) if selected else set()
            for index in range(len(self.albums)):
                self.table.item(str(index), text=self.row_text(index))
            self.update_selection()

    def launch(self, work, result_type):
        self.busy = True
        self.get_button.configure(state='disabled')
        self.update_selection()

        def run():
            try:
                self.events.put((result_type, work()))
            except Exception as error:
                self.events.put(('error', str(error)))
            finally:
                self.events.put(('idle', None))

        Thread(target=run, daemon=True).start()

    def get_albums(self):
        key = self.selection_key()
        try:
            address = album_address(key[0])
        except ValueError as error:
            messagebox.showerror('相册地址', str(error), parent=self.root)
            return
        self.source = None
        self.status.set('正在获取相册…')
        self.progress['value'] = 0
        self.launch(lambda: (key, find_albums(address, key[1])), 'albums')

    def start_download(self):
        if self.busy or not self.checked or self.source != self.selection_key():
            return
        try:
            minimum = int(self.width.get()) if self.mode.get() == 'width' else 0
            if self.mode.get() == 'width' and minimum < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror('图片尺寸', '请输入大于 0 的整数像素值。', parent=self.root)
            return
        target = self.folder.get().strip().strip('"')
        if not target:
            messagebox.showerror('保存目录', '请选择保存目录。', parent=self.root)
            return
        folder = Path(target).expanduser().absolute()
        self.last_folder = folder
        albums = [self.albums[index] for index in sorted(self.checked)]
        self.progress['value'] = 0
        self.errors.clear()
        self.status.set('正在准备下载…')
        self.launch(lambda: download(albums, folder, minimum, lambda kind, value: self.events.put((kind, value))), 'done')

    def handle_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'albums':
                    self.source, self.albums = value
                    self.checked.clear()
                    self.table.delete(*self.table.get_children())
                    for index in range(len(self.albums)):
                        self.table.insert('', 'end', iid=str(index), text=self.row_text(index))
                    self.status.set(f'找到 {len(self.albums)} 个相册，请勾选要下载的相册。' if self.albums else '没有找到匹配的相册。')
                elif kind == 'progress':
                    done, total = value
                    self.progress['value'] = 100 * done / total
                elif kind == 'log':
                    self.errors.append(value)
                elif kind in ('done', 'status'):
                    self.status.set(value)
                    if kind == 'done' and self.errors:
                        messagebox.showwarning('部分下载失败', value + '\n\n' + '\n'.join(self.errors[:6]), parent=self.root)
                elif kind == 'error':
                    self.status.set('操作失败，请检查地址、网络或保存目录。')
                    messagebox.showerror('操作失败', value, parent=self.root)
                elif kind == 'idle':
                    self.busy = False
                    self.get_button.configure(state='normal')
                    self.update_selection()
        except Empty:
            self.root.after(60, self.handle_events)

    def close(self):
        if not self.busy or messagebox.askyesno('退出', '当前任务还在运行，确定退出吗？', parent=self.root):
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
