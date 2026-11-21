# Yupoo 相册下载器

根据相册标题关键词筛选并下载 Yupoo 分类中的图片。默认分类地址写在源码中。

## 使用

运行 `yupoo_26_27_downloader.py`，输入一个关键词；也可以用逗号分隔多个关键词，任一关键词匹配即会下载。直接回车默认使用 `26,27`。接着可输入保存目录，直接回车则保存到程序旁的 `Yupoo下载` 文件夹。

已存在的图片会跳过；程序会生成 `下载清单.txt`。

## 打包成单文件 exe（Windows）

```powershell
python -m pip install pyinstaller
pyinstaller --onefile --console --name Yupoo_相册下载器 yupoo_26_27_downloader.py
```

生成文件位于 `dist` 目录。
