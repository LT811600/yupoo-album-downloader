# Yupoo 相册下载器

## 图形界面

运行 `python yupoo_gui.py`，输入 Yupoo 相册或分类地址，再点「获取相册」。关键词留空时列出该地址下的全部相册。多个关键词用逗号分隔，匹配任意一个即可。

可逐个勾选，也可全选或取消全选。选择「原图」时不限制宽度。选择「宽度等于或大于」时，只保存达到指定宽度的原图。点击「开始下载」后，程序按相册保存图片、跳过已存在的图片，并生成下载清单。

## 打包 Windows 单文件 exe

在带有 Tkinter 的 Python 环境运行：

```powershell
python -m pip install pyinstaller
python -m PyInstaller --onefile --windowed --name Yupoo_相册下载器_GUI yupoo_gui.py
```

生成文件位于 `dist`。原命令行入口是 `yupoo_26_27_downloader.py`。
