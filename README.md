# pdf2ieee

> 批量把论文 PDF 转换成符合 **IEEE Reference Guide v3.28.2025** 规范的 BibTeX 条目

给一堆论文 PDF，自动识别 DOI / arXiv ID / 标题，查询 Crossref / arXiv / OpenAlex 拿到 BibTeX，再按 IEEE 格式做字段清理、期刊/会议缩写替换、专有名词大写保护，直接输出可用 `\bibliographystyle{IEEEtran}` 编译的 `.bib` 文件。

## 特性

- **三级文本抽取链**：PyMuPDF → PyPDF2 → Tesseract OCR 自动兜底，扫描版 PDF 也能处理
- **多源元数据查询**：DOI 走 Crossref，arXiv 预印本走 arXiv API，Crossref 未命中自动切 OpenAlex
- **文件名兜底**：无文本层的扫描 PDF 会用文件名做模糊搜索
- **自带 50+ IEEE 期刊、30+ IEEE 会议**的标准缩写映射表
- **条目级字段清理**：按 `@article` / `@inproceedings` / `@book` / `@misc` 等分类，保留必需字段、删除噪声字段
- **专有名词保护**：LiDAR、CNN、ICRA、KITTI 等术语自动加 `{}` 防止被 BibTeX 小写化
- **`--fix-bib` 模式**：对已有 `.bib` 文件做一轮重新清洗

## 安装

### 必要依赖

至少安装一个 PDF 库：

```bash
pip install PyMuPDF requests    # 推荐，抽取质量更高
# 或
pip install PyPDF2 requests     # 备选
```

### OCR 可选依赖

处理扫描版 PDF 时才需要。没装也能跑，只是遇到扫描件会落到"文件名兜底"：

```bash
pip install pytesseract pdf2image
```

系统包：

- **macOS**：`brew install tesseract poppler`
- **Ubuntu/Debian**：`sudo apt install tesseract-ocr poppler-utils`
- **Windows**：[tesseract](https://github.com/UB-Mannheim/tesseract/wiki) + [poppler](https://github.com/oschwartz10612/poppler-windows/releases)

## 快速开始

```bash
# 处理一整个文件夹（递归找 *.pdf）
python pdf2ieee.py ./papers/

# 处理指定的几个 PDF
python pdf2ieee.py a.pdf b.pdf c.pdf

# 指定输出文件名
python pdf2ieee.py ./papers/ -o my_refs.bib

# 对已有的 .bib 做一轮清洗（加缩写 / 删噪声字段 / 保护大写）
python pdf2ieee.py --fix-bib old.bib -o new.bib
```

### 在论文里引用

```latex
\bibliographystyle{IEEEtran}
\bibliography{references}
```

然后 `pdflatex → bibtex → pdflatex → pdflatex` 编译。

## 工作流程

对每个 PDF，先抽文本：

```
PyMuPDF (fitz)  ──►  文本够长？ ── 是 ──► 用这个文本
     │ 否
     ▼
PyPDF2 备选     ──►  文本够长？ ── 是 ──► 用这个文本
     │ 否
     ▼
Tesseract OCR  ──► 用 OCR 的结果
```

再走匹配链：

1. **DOI 正则**（前 2 页）→ Crossref API → BibTeX
2. **arXiv 正则**（带 `arXiv:` 前缀严格匹配）→ arXiv API → 拼 BibTeX
3. **标题抽取**（正文首页猜 / 失败则文件名清洗）→ Crossref 模糊搜索 → OpenAlex 兜底

拿到原始 BibTeX 后统一做后处理：

```
格式美化 → 字段清理 → IEEE 期刊缩写 → IEEE 会议缩写 → 专有名词大写保护
```

## 效果示例

Crossref 原始返回：

```bibtex
@article{Charron_2018,
    title={De-noising of Lidar Point Clouds Corrupted by Snowfall},
    ISSN={},
    url={http://dx.doi.org/10.1109/CRV.2018.00043},
    DOI={10.1109/crv.2018.00043},
    booktitle={2018 15th Conference on Computer and Robot Vision (CRV)},
    publisher={IEEE},
    author={Charron, Nicholas and Phillips, Stephen and Waslander, Steven L.},
    year={2018},
    month=may,
    pages={254-261}
}
```

pdf2ieee 清洗后：

```bibtex
@inproceedings{Charron_2018,
  title     = {{De-Noising} of {LiDAR} Point Clouds Corrupted by Snowfall},
  DOI       = {10.1109/crv.2018.00043},
  booktitle = {Proc. Conf. Comput. Robot Vis. ({CRV})},
  author    = {Charron, Nicholas and Phillips, Stephen and Waslander, Steven L.},
  year      = {2018},
  month     = may,
  pages     = {254-261}
}
```

## IEEE Reference Guide 合规性

字段保留/删除规则对齐 IEEE Reference Guide v3.28.2025：

| 条目类型 | 保留关键字段 | 额外删除字段 |
|---|---|---|
| `@article` | journal, volume, number, pages, month, year, doi | url, publisher, address, isbn, note, editor |
| `@inproceedings` | booktitle, pages, month, year, doi | url, publisher, address, organization, location, series |
| `@book` / `@inbook` | editor, publisher, address, series | isbn, note |
| `@techreport` | institution, url | isbn, note, editor |
| `@manual` / `@standard` | organization, url | isbn, note, editor |
| `@misc` (arXiv 预印本) | note, howpublished | isbn, editor |

所有条目都会删除这些噪声字段：`issn`, `abstract`, `keywords`, `language`, `copyright`, `month_numeric`, `urldate`。

## 扩展期刊 / 会议缩写表

直接改源码里的两个字典即可：

```python
IEEE_JOURNAL_MAP = {
    "IEEE Transactions on Automatic Control": "{IEEE} Trans. Automat. Contr.",
    # 加你自己的...
}

IEEE_CONFERENCE_MAP = {
    # key 必须是 _normalize_conference_name 处理后的小写形式
    # （去掉年份、序号、括号缩写、"Proceedings of" 等冠词）
    "ieee international conference on robotics and automation":
        "Proc. {IEEE} Int. Conf. Robot. Autom. ({ICRA})",
}
```

会议的 key 写法注意要**去掉年份、序号、括号缩写**，比如 Crossref 返回的 `"2018 15th Conference on Computer and Robot Vision (CRV)"` 对应的 key 应该写成 `"conference on computer and robot vision"`。

## 已知局限

- **不注册 Crossref DOI 的会议**：AAAI、NeurIPS、ICML、ICLR 等。如果论文也没上 arXiv，只能靠标题搜索兜底，命中率不保证。建议手动从 DBLP 或会议官网导出 BibTeX。
- **扫描 PDF 且没装 OCR**：只能靠文件名做标题搜索。文件名与论文标题差异大的会挂——尽量保留原始描述性文件名。
- **PDF 抽取串词**：偶尔会遇到 DOI 和正文首词粘在一起的情况（如 `10.1109/LRA.2026.3653382that`），代码里已有 `_doi_candidates` 做截断重试，一般能救回来。
