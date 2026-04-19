import re
import requests
import sys
import os
import glob
import xml.etree.ElementTree as ET

# ──────────────────────────────────────────────
# PDF 文本提取依赖：优先 PyMuPDF，其次 PyPDF2，扫描件走 OCR
# ──────────────────────────────────────────────

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

if not (HAS_FITZ or HAS_PYPDF2):
    print("[!] 必须安装至少一个 PDF 库：")
    print("    pip install PyMuPDF   （推荐，抽取质量更高）")
    print("    pip install PyPDF2    （备选）")
    sys.exit(1)

# ──────────────────────────────────────────────
# IEEE 期刊全称 → 标准缩写（直接硬编码，无需 IEEEabrv.bib）
# ──────────────────────────────────────────────

IEEE_JOURNAL_MAP = {
    "IEEE Transactions on Automatic Control":                        "{IEEE} Trans. Automat. Contr.",
    "IEEE Transactions on Aerospace and Electronic Systems":         "{IEEE} Trans. Aerosp. Electron. Syst.",
    "IEEE Transactions on Antennas and Propagation":                 "{IEEE} Trans. Antennas Propagat.",
    "IEEE Transactions on Biomedical Engineering":                   "{IEEE} Trans. Biomed. Eng.",
    "IEEE Transactions on Circuits and Systems":                     "{IEEE} Trans. Circuits Syst.",
    "IEEE Transactions on Communications":                           "{IEEE} Trans. Commun.",
    "IEEE Transactions on Computers":                                "{IEEE} Trans. Comput.",
    "IEEE Transactions on Consumer Electronics":                     "{IEEE} Trans. Consumer Electron.",
    "IEEE Transactions on Control Systems Technology":               "{IEEE} Trans. Contr. Syst. Technol.",
    "IEEE Transactions on Electron Devices":                         "{IEEE} Trans. Electron Devices",
    "IEEE Transactions on Electromagnetic Compatibility":            "{IEEE} Trans. Electromagn. Compat.",
    "IEEE Transactions on Geoscience and Remote Sensing":            "{IEEE} Trans. Geosci. Remote Sens.",
    "IEEE Transactions on Image Processing":                         "{IEEE} Trans. Image Process.",
    "IEEE Transactions on Industrial Electronics":                   "{IEEE} Trans. Ind. Electron.",
    "IEEE Transactions on Industry Applications":                    "{IEEE} Trans. Ind. Applicat.",
    "IEEE Transactions on Information Theory":                       "{IEEE} Trans. Inform. Theory",
    "IEEE Transactions on Instrumentation and Measurement":          "{IEEE} Trans. Instrum. Meas.",
    "IEEE Transactions on Magnetics":                                "{IEEE} Trans. Magn.",
    "IEEE Transactions on Medical Imaging":                          "{IEEE} Trans. Med. Imag.",
    "IEEE Transactions on Microwave Theory and Techniques":          "{IEEE} Trans. Microwave Theory Tech.",
    "IEEE Transactions on Neural Networks":                          "{IEEE} Trans. Neural Networks",
    "IEEE Transactions on Neural Networks and Learning Systems":     "{IEEE} Trans. Neural Netw. Learn. Syst.",
    "IEEE Transactions on Pattern Analysis and Machine Intelligence":"{IEEE} Trans. Pattern Anal. Mach. Intell.",
    "IEEE Transactions on Power Electronics":                        "{IEEE} Trans. Power Electron.",
    "IEEE Transactions on Reliability":                              "{IEEE} Trans. Rel.",
    "IEEE Transactions on Robotics":                                 "{IEEE} Trans. Robot.",
    "IEEE Transactions on Robotics and Automation":                  "{IEEE} Trans. Robot. Automat.",
    "IEEE Transactions on Signal Processing":                        "{IEEE} Trans. Signal Process.",
    "IEEE Transactions on Systems, Man, and Cybernetics":            "{IEEE} Trans. Syst., Man, Cybern.",
    "IEEE Transactions on Vehicular Technology":                     "{IEEE} Trans. Veh. Technol.",
    "IEEE Transactions on Wireless Communications":                  "{IEEE} Trans. Wireless Commun.",
    "IEEE Transactions on Mechatronics":                             "{IEEE/ASME} Trans. Mechatron.",
    "IEEE/ACM Transactions on Networking":                           "{IEEE/ACM} Trans. Netw.",
    "IEEE Journal on Selected Areas in Communications":              "{IEEE} J. Select. Areas Commun.",
    "IEEE Journal of Selected Topics in Signal Processing":          "{IEEE} J. Select. Topics Signal Process.",
    "IEEE Journal of Solid-State Circuits":                          "{IEEE} J. Solid-State Circuits",
    "IEEE Robotics and Automation Letters":                          "{IEEE} Robot. Autom. Lett.",
    "IEEE Electron Device Letters":                                  "{IEEE} Electron Device Lett.",
    "IEEE Photonics Technology Letters":                             "{IEEE} Photon. Technol. Lett.",
    "IEEE Signal Processing Letters":                                "{IEEE} Signal Process. Lett.",
    "IEEE Communications Letters":                                   "{IEEE} Commun. Lett.",
    "IEEE Wireless Communications Letters":                          "{IEEE} Wireless Commun. Lett.",
    "IEEE Access":                                                   "{IEEE} Access",
    "IEEE Sensors Journal":                                          "{IEEE} Sensors J.",
    "IEEE Signal Processing Magazine":                               "{IEEE} Signal Process. Mag.",
    "IEEE Communications Magazine":                                  "{IEEE} Commun. Mag.",
    "IEEE Spectrum":                                                 "{IEEE} Spectr.",
    "IEEE Micro":                                                    "{IEEE} Micro",
    "IEEE Personal Communications":                                  "{IEEE} Personal Commun. Mag.",
    "IEEE Wireless Communications":                                  "{IEEE} Wireless Commun. Mag.",
    "IEEE Network":                                                  "{IEEE} Network",
    "IEEE Internet of Things Journal":                               "{IEEE} Internet Things J.",
}

# ──────────────────────────────────────────────
# IEEE 会议全称 → 标准缩写（用于 @inproceedings 的 booktitle 字段）
# key 必须使用 _normalize_conference_name 后的小写形式（去掉前缀年份/序号/括号缩写）
# ──────────────────────────────────────────────

IEEE_CONFERENCE_MAP = {
    # 机器人 & 智能车
    "ieee international conference on robotics and automation":
        "Proc. {IEEE} Int. Conf. Robot. Autom. ({ICRA})",
    "international conference on robotics and automation":
        "Proc. {IEEE} Int. Conf. Robot. Autom. ({ICRA})",
    "ieee/rsj international conference on intelligent robots and systems":
        "Proc. {IEEE/RSJ} Int. Conf. Intell. Robots Syst. ({IROS})",
    "international conference on intelligent robots and systems":
        "Proc. {IEEE/RSJ} Int. Conf. Intell. Robots Syst. ({IROS})",
    "ieee intelligent vehicles symposium":
        "Proc. {IEEE} Intell. Veh. Symp. ({IV})",
    "intelligent vehicles symposium":
        "Proc. {IEEE} Intell. Veh. Symp. ({IV})",
    "ieee international conference on intelligent transportation systems":
        "Proc. {IEEE} Int. Conf. Intell. Transp. Syst. ({ITSC})",
    "international conference on intelligent transportation systems":
        "Proc. {IEEE} Int. Conf. Intell. Transp. Syst. ({ITSC})",
    "ieee international conference on advanced robotics and its social impacts":
        "Proc. {IEEE} Int. Conf. Adv. Robot. Soc. Impacts ({ARSO})",

    # 计算机视觉 & 机器学习
    "ieee conference on computer vision and pattern recognition":
        "Proc. {IEEE/CVF} Conf. Comput. Vis. Pattern Recognit. ({CVPR})",
    "ieee/cvf conference on computer vision and pattern recognition":
        "Proc. {IEEE/CVF} Conf. Comput. Vis. Pattern Recognit. ({CVPR})",
    "ieee computer society conference on computer vision and pattern recognition":
        "Proc. {IEEE/CVF} Conf. Comput. Vis. Pattern Recognit. ({CVPR})",
    "conference on computer vision and pattern recognition":
        "Proc. {IEEE/CVF} Conf. Comput. Vis. Pattern Recognit. ({CVPR})",
    "ieee international conference on computer vision":
        "Proc. {IEEE/CVF} Int. Conf. Comput. Vis. ({ICCV})",
    "ieee/cvf international conference on computer vision":
        "Proc. {IEEE/CVF} Int. Conf. Comput. Vis. ({ICCV})",
    "international conference on computer vision":
        "Proc. {IEEE/CVF} Int. Conf. Comput. Vis. ({ICCV})",
    "european conference on computer vision":
        "Proc. Eur. Conf. Comput. Vis. ({ECCV})",
    "ieee winter conference on applications of computer vision":
        "Proc. {IEEE/CVF} Winter Conf. Appl. Comput. Vis. ({WACV})",
    "british machine vision conference":
        "Proc. Brit. Mach. Vis. Conf. ({BMVC})",
    "conference on neural information processing systems":
        "Proc. Adv. Neural Inf. Process. Syst. ({NeurIPS})",
    "advances in neural information processing systems":
        "Proc. Adv. Neural Inf. Process. Syst. ({NeurIPS})",
    "international conference on machine learning":
        "Proc. Int. Conf. Mach. Learn. ({ICML})",
    "international conference on learning representations":
        "Proc. Int. Conf. Learn. Representations ({ICLR})",
    "aaai conference on artificial intelligence":
        "Proc. {AAAI} Conf. Artif. Intell.",
    "international joint conference on artificial intelligence":
        "Proc. Int. Joint Conf. Artif. Intell. ({IJCAI})",

    # 图像 / 模式识别 / 机器人视觉
    "conference on computer and robot vision":
        "Proc. Conf. Comput. Robot Vis. ({CRV})",
    "international conference on pattern recognition":
        "Proc. Int. Conf. Pattern Recognit. ({ICPR})",
    "ieee international conference on image processing":
        "Proc. {IEEE} Int. Conf. Image Process. ({ICIP})",
    "international conference on 3d vision":
        "Proc. Int. Conf. {3D} Vis. ({3DV})",

    # 信号处理 / 通信
    "ieee international conference on acoustics, speech and signal processing":
        "Proc. {IEEE} Int. Conf. Acoust. Speech Signal Process. ({ICASSP})",
    "international conference on acoustics, speech and signal processing":
        "Proc. {IEEE} Int. Conf. Acoust. Speech Signal Process. ({ICASSP})",
    "ieee global communications conference":
        "Proc. {IEEE} Global Commun. Conf. ({GLOBECOM})",
    "ieee international conference on communications":
        "Proc. {IEEE} Int. Conf. Commun. ({ICC})",

    # 车载 / 电力电子 / 控制
    "ieee vehicular technology conference":
        "Proc. {IEEE} Veh. Technol. Conf. ({VTC})",
    "ieee conference on decision and control":
        "Proc. {IEEE} Conf. Decis. Control ({CDC})",
    "american control conference":
        "Proc. Amer. Control Conf. ({ACC})",

    # SIGGRAPH / 图形学
    "acm siggraph":                       "Proc. {ACM} {SIGGRAPH}",
    "eurographics":                       "Proc. Eurographics",

    # 自然语言处理
    "annual meeting of the association for computational linguistics":
        "Proc. Annu. Meeting Assoc. Comput. Linguistics ({ACL})",
    "conference on empirical methods in natural language processing":
        "Proc. Conf. Empirical Methods Natural Lang. Process. ({EMNLP})",
}

# ──────────────────────────────────────────────
# 专有名词大写保护列表
# ──────────────────────────────────────────────

PROTECTED_TERMS = [
    "LiDAR", "LIDAR", "CNN", "RNN", "LSTM", "GAN", "SVM",
    "DSOR", "DROR", "PCL", "SLAM", "KITTI", "GPS", "IMU",
    "RGB", "RGB-D", "3D", "2D", "UAV", "UGV", "ROS",
    "IEEE", "ICRA", "IROS", "CVPR", "ICCV", "NeurIPS",
    "arXiv", "DOI", "API",
    "LIO-SAM", "PointNet", "VoxelNet", "PointPillars",
    "DeepLab", "ResNet", "VGG", "YOLO",
    "de-noising", "De-Noising",
]

# ──────────────────────────────────────────────
# 后处理函数
# ──────────────────────────────────────────────

def apply_ieee_journal_macros(bibtex: str) -> str:
    """将 journal 字段的 IEEE 全称替换为带 {} 保护的标准缩写。"""
    def replace_journal(m):
        field_name  = m.group(1)
        journal_val = m.group(2).strip().rstrip(',').strip()
        field_end   = m.group(3)
        for full_name, abbr in IEEE_JOURNAL_MAP.items():
            if journal_val.lower() == full_name.lower():
                return f"{field_name}{{{abbr}}}{field_end}"
        return m.group(0)

    return re.sub(
        r'(journal\s*=\s*)\{([^}]+)\}(,?\s*\n?)',
        replace_journal,
        bibtex,
        flags=re.IGNORECASE
    )


def _normalize_conference_name(name: str) -> str:
    """
    将 Crossref 返回的会议名规范化，用于字典模糊匹配。

    典型输入：
      "2018 IEEE Intelligent Vehicles Symposium (IV)"
      "2018 21st International Conference on Intelligent Transportation Systems (ITSC)"
      "2016 IEEE Conference on Computer Vision and Pattern Recognition (CVPR)"

    处理步骤：
      1. 去掉首部 4 位年份
      2. 去掉序号前缀，如 "15th"、"21st"、"3rd"、"1st"
      3. 去掉结尾括号缩写，如 "(ITSC)"、"(CVPR)"
      4. 去掉 "Proceedings of the"、"Proc." 之类冠词
      5. 去掉末尾 "Proceedings"
      6. 统一小写、压缩空白
    """
    s = name.strip()

    # 结尾括号缩写：(ITSC) (CVPR) ...
    s = re.sub(r'\s*\([A-Za-z0-9/\-]+\)\s*$', '', s)

    # 开头冠词
    s = re.sub(r'^\s*(proceedings of the|proceedings of|proc\.?\s*of\s*the|proc\.?\s*of|proc\.?)\s+',
               '', s, flags=re.IGNORECASE)

    # 开头年份
    s = re.sub(r'^\s*(19|20)\d{2}\s+', '', s)

    # 开头序号（15th / 21st / 3rd / 1st）
    s = re.sub(r'^\s*\d+(st|nd|rd|th)\s+', '', s, flags=re.IGNORECASE)

    # 再尝试一次年份（有些是 "15th 2018 ..." 这种倒序）
    s = re.sub(r'^\s*(19|20)\d{2}\s+', '', s)

    # 结尾 "Proceedings"
    s = re.sub(r'\s+proceedings\s*$', '', s, flags=re.IGNORECASE)

    # 压缩空白
    s = re.sub(r'\s+', ' ', s).strip().lower()
    return s


def apply_ieee_conference_macros(bibtex: str) -> str:
    """将 booktitle 字段（和 series 字段）的会议全称替换为 IEEE 标准缩写。"""
    def replace_booktitle(m):
        field_name = m.group(1)
        raw_val    = m.group(2).strip().rstrip(',').strip()
        field_end  = m.group(3)

        normalized = _normalize_conference_name(raw_val)

        # 先精确匹配
        if normalized in IEEE_CONFERENCE_MAP:
            return f"{field_name}{{{IEEE_CONFERENCE_MAP[normalized]}}}{field_end}"

        # 再做一次"被包含"匹配，处理 "2018 15th Conference on Computer and Robot Vision (CRV)"
        # 这类清洗后仍可能带多余字样的情况
        for full_name, abbr in IEEE_CONFERENCE_MAP.items():
            if full_name in normalized:
                return f"{field_name}{{{abbr}}}{field_end}"

        return m.group(0)

    # booktitle（会议论文）
    bibtex = re.sub(
        r'(booktitle\s*=\s*)\{([^}]+)\}(,?\s*\n?)',
        replace_booktitle,
        bibtex,
        flags=re.IGNORECASE
    )
    # series（偶尔 Crossref 把会议放在 series 里）
    bibtex = re.sub(
        r'(series\s*=\s*)\{([^}]+)\}(,?\s*\n?)',
        replace_booktitle,
        bibtex,
        flags=re.IGNORECASE
    )
    return bibtex


def protect_title_caps(bibtex: str) -> str:
    """对 title 字段中的专有名词加 {} 大写保护。"""
    def process_title_value(title_val: str) -> str:
        for term in PROTECTED_TERMS:
            escaped = re.escape(term)
            pattern = re.compile(r'(?<!\{)' + escaped + r'(?!\})', re.IGNORECASE)
            title_val = pattern.sub(lambda m: '{' + m.group(0) + '}', title_val)
        return title_val

    def replace_title(m):
        return m.group(1) + process_title_value(m.group(2)) + m.group(3)

    return re.sub(
        r'(title\s*=\s*\{)(.*?)(\})',
        replace_title,
        bibtex,
        flags=re.DOTALL | re.IGNORECASE
    )


def strip_redundant_fields(bibtex: str) -> str:
    """
    按条目类型分层清理字段，对齐 IEEE Reference Guide v3.28.2025。

    规则出处（Guide 章节）：
      §II.M Periodicals   "DOIs are included, when provided by the author" → 保留 doi
      §II.T Websites      "[Online]. Available: URL"                       → @misc/@online 保留 url
      §II.B Book          editor 在书类条目里是必要字段                      → @book/@inbook/@incollection 保留 editor
      §II.N Reports       Report online 需要 URL                           → @techreport 保留 url
      §II.P Standards     Standard online 需要 URL                         → @standard/@manual 保留 url
      §II.S Preprint      "year, arXiv:xxxx.xxxxx"                         → @misc 保留 note/howpublished

    @article 这类期刊条目：只保留 journal/volume/number/pages/month/year/doi + 基础字段，
    其余全删（address/publisher/issn/isbn 这些 IEEEtran.bst 本来也不会输出）。
    """
    # 识别条目类型
    m = re.match(r'\s*@(\w+)\s*\{', bibtex)
    entry_type = m.group(1).lower() if m else ''

    # 元数据/抓取回来的噪声字段，对所有条目类型都删
    always_drop = ['issn', 'abstract', 'keywords', 'language',
                   'copyright', 'month_numeric', 'urldate']

    # 期刊文章 / 早期访问 —— 按 §II.M，保留 doi
    if entry_type == 'article':
        drop = always_drop + ['url', 'publisher', 'address',
                              'isbn', 'note', 'editor']
    # 会议论文 —— 按 §II.C，保留 doi，去掉出版社/地址
    elif entry_type in ('inproceedings', 'conference'):
        drop = always_drop + ['url', 'publisher', 'address',
                              'organization', 'location', 'editor',
                              'isbn', 'note', 'series']
    # 书 / 书中章节 —— 按 §II.B，保留 editor / publisher / address / series
    elif entry_type in ('book', 'inbook', 'incollection', 'booklet'):
        drop = always_drop + ['isbn', 'note']
    # 技术报告 —— 按 §II.N，online 版需要 url
    elif entry_type == 'techreport':
        drop = always_drop + ['isbn', 'note', 'editor']
    # 手册 / 标准 —— 按 §II.I, §II.P，online 版需要 url
    elif entry_type in ('manual', 'standard'):
        drop = always_drop + ['isbn', 'note', 'editor']
    # 网页 / 数据集 / 软件 / arXiv 预印本 等 misc 类 —— 必须保留 url/howpublished/note
    elif entry_type in ('misc', 'online', 'electronic', 'software', 'dataset'):
        drop = always_drop + ['isbn', 'editor']
    # 学位论文、专利等其他类型
    else:
        drop = always_drop + ['isbn']

    for field in drop:
        bibtex = re.sub(
            r',\s*\b' + re.escape(field) + r'\b\s*=\s*(?:\{[^{}]*\}|"[^"]*")',
            '',
            bibtex,
            flags=re.IGNORECASE | re.DOTALL
        )
    return bibtex


def prettify_bibtex(bibtex: str) -> str:
    """将单行压缩格式 BibTeX 整理成多行对齐格式。"""
    if bibtex.count('\n') > 3:
        return bibtex

    header_match = re.match(r'(@\w+\{)([^,]+),', bibtex)
    if not header_match:
        return bibtex

    entry_type = header_match.group(1)
    key = header_match.group(2).strip()
    body = bibtex[header_match.end():]
    body = body.rstrip().rstrip('}').rstrip()

    field_pattern = re.compile(
        r'(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|"[^"]*"|[^,}]+)',
        re.DOTALL
    )
    fields = field_pattern.findall(body)
    if not fields:
        return bibtex

    max_key_len = max(len(f[0]) for f in fields)
    lines = [f"{entry_type}{key},"]
    for fname, fvalue in fields:
        fvalue = fvalue.strip().rstrip(',')
        padding = ' ' * (max_key_len - len(fname))
        lines.append(f"  {fname}{padding} = {fvalue},")
    lines[-1] = lines[-1].rstrip(',')
    lines.append("}")
    return '\n'.join(lines)


def postprocess(bibtex: str) -> str:
    """依次执行：格式美化 → 删除冗余字段 → IEEE 期刊缩写 → IEEE 会议缩写 → 专有名词大写保护"""
    bibtex = prettify_bibtex(bibtex)
    bibtex = strip_redundant_fields(bibtex)
    bibtex = apply_ieee_journal_macros(bibtex)
    bibtex = apply_ieee_conference_macros(bibtex)
    bibtex = protect_title_caps(bibtex)
    return bibtex

# ═══════════════════════════════════════════════════════════════
# 【改动 1】统一 PDF 文本提取：PyMuPDF → PyPDF2 → OCR 三级兜底链
# ═══════════════════════════════════════════════════════════════

def _extract_with_fitz(pdf_path, max_pages=2):
    """PyMuPDF 提取，对 IEEE/Springer 等复杂排版效果明显好于 PyPDF2。"""
    if not HAS_FITZ:
        return ''
    try:
        with fitz.open(pdf_path) as doc:
            n = min(max_pages, doc.page_count)
            return '\n'.join(doc[i].get_text() for i in range(n))
    except Exception as e:
        print(f"  [-] PyMuPDF 读取失败: {e}")
        return ''


def _extract_with_pypdf2(pdf_path, max_pages=2):
    """PyPDF2 提取，作为 fitz 的备选。"""
    if not HAS_PYPDF2:
        return ''
    try:
        with open(pdf_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            n = min(max_pages, len(reader.pages))
            texts = []
            for i in range(n):
                t = reader.pages[i].extract_text() or ''
                texts.append(t)
            return '\n'.join(texts)
    except Exception as e:
        print(f"  [-] PyPDF2 读取失败: {e}")
        return ''


def _extract_with_ocr(pdf_path, max_pages=2):
    """
    OCR 兜底：仅在前两种方法抽不到足够文本时触发（扫描版 PDF）。
    需要 pip install pytesseract pdf2image，以及系统包 tesseract-ocr、poppler-utils。
    未安装时静默跳过，不影响主流程。
    """
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        return ''
    try:
        images = convert_from_path(pdf_path, dpi=200,
                                   first_page=1, last_page=max_pages)
        return '\n'.join(pytesseract.image_to_string(img, lang='eng') for img in images)
    except Exception as e:
        print(f"  [-] OCR 失败: {e}")
        return ''


def extract_text_from_pdf(pdf_path, max_pages=2, ocr_threshold=200):
    """
    三级文本提取链：
      1) PyMuPDF (fitz)     —— 质量最好，解决 PyPDF2 在 DOI 处插入换行的问题
      2) PyPDF2             —— fitz 失败或未安装时兜底
      3) OCR (tesseract)    —— 前两步抽不到足够文本时启用（扫描版 PDF）

    ocr_threshold: 非 OCR 方法抽出的文本低于这个字符数就触发 OCR。
    """
    text = _extract_with_fitz(pdf_path, max_pages)

    if len(text.strip()) < ocr_threshold:
        text2 = _extract_with_pypdf2(pdf_path, max_pages)
        if len(text2.strip()) > len(text.strip()):
            text = text2

    if len(text.strip()) < ocr_threshold:
        print(f"  [i] 直接提取仅 {len(text.strip())} chars，尝试 OCR")
        ocr_text = _extract_with_ocr(pdf_path, max_pages)
        if len(ocr_text.strip()) > len(text.strip()):
            text = ocr_text
            print(f"  [+] OCR 成功提取 {len(text.strip())} chars")

    return text

# ══════════════════════════════════════════════════════════════
# 【改动 2】DOI / arXiv / Title 提取函数改为"从文本中提取"
# 这样 process_single_pdf 只提取一次文本，后续都复用，同时避免
# 对同一个扫描 PDF 反复触发 OCR。
# ══════════════════════════════════════════════════════════════

def _clean_doi_tail(doi: str) -> str:
    """去除 DOI 末尾常见的标点。"""
    return doi.rstrip('.,;:)]}>\"\'')


def _doi_candidates(doi: str):
    """
    生成 DOI 查询候选，由长到短依次尝试。
    主要用于修复 PDF 抽取把 DOI 和下一段首词粘在一起的情况，
    例如 '10.1109/LRA.2026.3653382that' → '10.1109/LRA.2026.3653382'。
    """
    doi = _clean_doi_tail(doi)
    yield doi
    # 如果 DOI 以"数字 + 字母粘连"结尾，砍掉字母尾
    m = re.match(r'^(.*\d)[A-Za-z]+$', doi)
    if m and m.group(1) != doi:
        yield m.group(1)


def extract_doi_from_text(text):
    """
    从已提取的 PDF 文本里找 DOI。关键改动：先把所有空白（含换行、
    不间断空格 \\u00a0）压成单个空格，避免 PyPDF2 在 DOI 中间插入
    换行导致匹配失败。
    """
    if not text:
        return None
    # 跨行/特殊空白拼接：这是修复文件 1 的核心
    flat = re.sub(r'[\s\u00a0]+', ' ', text)
    doi_pattern = re.compile(r'\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b')
    matches = doi_pattern.findall(flat)
    for m in matches:
        doi = _clean_doi_tail(m)
        if '10.48550' not in doi:  # 排除 arXiv 的 Crossref DOI，优先走 arXiv 路径
            return doi
    return None


def _is_valid_arxiv_id(aid: str) -> bool:
    """
    校验 arXiv ID 合法性，兼容新旧两种格式。
    新格式 YYMM.NNNNN 要求 MM 在 01-12 之间，YY 在 07-99 之间（arXiv 新格式始于 2007-04）。
    旧格式形如 hep-th/9901001 或 cs.CV/0701001。
    """
    # 新格式
    m = re.match(r'^(\d{2})(\d{2})\.\d{4,5}$', aid)
    if m:
        yy, mm = int(m.group(1)), int(m.group(2))
        return 1 <= mm <= 12 and 7 <= yy <= 99
    # 旧格式
    if re.match(r'^[a-z\-]+(?:\.[A-Z]{2})?/\d{7}$', aid):
        return True
    return False


def extract_arxiv_id_from_text(text):
    """
    严格要求 'arXiv' 前缀才视为 arXiv ID，避免把 DOI 里的数字串误判。
    兼容新旧两种格式。
    """
    if not text:
        return None
    arxiv_pattern = re.compile(
        r'arXiv\s*[:.]?\s*'
        r'('
        r'\d{4}\.\d{4,5}(?:v\d+)?'          # 新格式
        r'|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}'   # 旧格式
        r')',
        re.IGNORECASE,
    )
    matches = arxiv_pattern.findall(text)
    for m in matches:
        aid = m if isinstance(m, str) else m[0]
        # 去掉版本后缀再做合法性校验
        aid_base = re.sub(r'v\d+$', '', aid)
        if _is_valid_arxiv_id(aid_base):
            return aid_base
    return None


def extract_title_from_text(text):
    """
    从 PDF 首页正文猜标题。
    策略：去掉页眉、页码、作者行之后，取前几行拼接。
    """
    if not text:
        return None

    lines = [l.strip() for l in text.split('\n') if l.strip()]
    header_kw = re.compile(
        r'(IEEE TRANSACTIONS|IEEE ROBOTICS|VOL\.|NO\.|Proceedings of|'
        r'Conference on (Computer|Robot|Intelligent|Machine)|Copyright|©|ISSN|'
        r'2377-|2162-|Authorized licensed|Downloaded on|'
        r'The (Thirty|Fortieth|Fortyfirst|AAAI)|AAAI-\d|'
        r'arXiv:|Manuscript received)',
        re.IGNORECASE
    )
    cands = []
    for l in lines[:30]:
        if len(l) < 10:
            continue
        if l.replace(' ', '').replace('.', '').isdigit():
            continue
        if header_kw.search(l):
            continue
        # 形似作者行：逗号多且含作者编号/上标
        if l.count(',') >= 3 and re.search(r'[\d*†‡§]', l):
            break
        cands.append(l)
        if len(' '.join(cands)) > 120:
            break
    return ' '.join(cands[:3]) if cands else None

# ══════════════════════════════════════════════════════════════
# 【改动 3】从文件名清洗出可用标题 —— 扫描版 PDF 最后的救命稻草
# ══════════════════════════════════════════════════════════════

def clean_filename_as_title(pdf_path):
    """
    把 '01_Some-paper_title (v2).pdf' 清成 'Some paper title'。
    用于 PDF 正文抽不到任何文本（扫描件）、正文标题解析又失败时兜底。
    """
    name = os.path.splitext(os.path.basename(pdf_path))[0]
    # 去掉开头编号：'01_' / '(1) ' / '[3]. '
    name = re.sub(r'^\s*[\[\(]?\d+[\]\)\.\-_\s]+', '', name)
    # 去掉括号及其中内容：'(v2)' '(1991)'
    name = re.sub(r'[\(\[].*?[\)\]]', '', name)
    # 分隔符统一成空格
    name = re.sub(r'[_\-]+', ' ', name)
    # 压缩空白
    name = re.sub(r'\s+', ' ', name).strip()
    return name if len(name) >= 10 else None

# ──────────────────────────────────────────────
# Crossref 查询（按 DOI / 按标题）—— 这部分逻辑保持不变
# ──────────────────────────────────────────────

def get_bibtex_by_doi(doi):
    """查询 Crossref，失败时自动尝试 DOI 截断候选。"""
    last_err = None
    for candidate in _doi_candidates(doi):
        url = f"https://api.crossref.org/works/{candidate}/transform/application/x-bibtex"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                if candidate != doi:
                    print(f"  [+] DOI 尾部清理：{doi} → {candidate}")
                bibtex = response.content.decode('utf-8')
                bibtex = bibtex.replace('\u2013', '--').replace('\u2014', '--')
                return bibtex
            elif response.status_code == 404:
                last_err = f"Crossref 未找到该 DOI: {candidate}"
                continue
            else:
                last_err = f"请求失败，状态码: {response.status_code}"
        except requests.exceptions.RequestException as e:
            last_err = f"网络请求错误: {e}"
    if last_err:
        print(f"  [-] {last_err}")
    return None


def get_bibtex_by_title_search(title):
    """用 Crossref 的 bibliographic 模糊搜索接口，按标题反查 DOI，再拉 BibTeX。"""
    url = "https://api.crossref.org/works"
    params = {'query.bibliographic': title, 'rows': 3}
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            return None
        items = response.json().get('message', {}).get('items', [])
        if not items:
            return None
        best = items[0]
        best_title = (best.get('title') or [''])[0].lower()
        q_words = set(re.findall(r'[a-z]{4,}', title.lower()))
        t_words = set(re.findall(r'[a-z]{4,}', best_title))
        if q_words and t_words and len(q_words & t_words) < 3:
            print(f"  [-] Crossref 标题搜索结果相关度过低（命中 '{best_title[:50]}...'）")
            return None
        found_doi = best.get('DOI')
        if not found_doi:
            return None
        print(f"  [+] Crossref 标题反查得到 DOI: {found_doi}")
        return get_bibtex_by_doi(found_doi)
    except requests.exceptions.RequestException as e:
        print(f"  [-] 标题搜索网络请求错误: {e}")
    except Exception as e:
        print(f"  [-] 解析标题搜索结果时出错: {e}")
    return None

# ══════════════════════════════════════════════════════════════
# 【改动 4】OpenAlex 标题搜索 —— Crossref 未命中时的第二来源
# 对 90 年代 IEEE TPAMI 等老论文覆盖明显好于 Crossref。
# ══════════════════════════════════════════════════════════════

def get_bibtex_by_openalex_title_search(title):
    """
    用 OpenAlex 按标题查，拿到 DOI 后再调 Crossref 取 BibTeX，
    保持输出格式和主流程一致。
    """
    url = "https://api.openalex.org/works"
    params = {"search": title, "per-page": 5}
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            return None
        items = response.json().get("results", [])
        if not items:
            return None
    except requests.exceptions.RequestException as e:
        print(f"  [-] OpenAlex 网络请求错误: {e}")
        return None
    except Exception as e:
        print(f"  [-] 解析 OpenAlex 响应时出错: {e}")
        return None

    # 用词集合做相关度校验，防止 OpenAlex 返回主题近似但非目标论文
    q_words = set(re.findall(r'[a-z]{4,}', title.lower()))
    for item in items:
        cand_title = (item.get('title') or '').lower()
        t_words = set(re.findall(r'[a-z]{4,}', cand_title))
        if q_words and t_words and len(q_words & t_words) < 3:
            continue
        doi_url = item.get('doi') or ''
        found_doi = doi_url.replace('https://doi.org/', '').strip() or None
        if not found_doi:
            continue
        print(f"  [+] OpenAlex 匹配得到 DOI: {found_doi}")
        bibtex = get_bibtex_by_doi(found_doi)
        if bibtex:
            return bibtex
    return None

# ──────────────────────────────────────────────
# arXiv API 查询 —— 逻辑保持不变
# ──────────────────────────────────────────────

def get_bibtex_by_arxiv_id(arxiv_id):
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"  [-] arXiv API 请求失败，状态码: {response.status_code}")
            return None

        root = ET.fromstring(response.content)
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom'
        }

        entry = root.find('atom:entry', ns)
        if entry is None:
            print(f"  [-] arXiv 未找到该 ID: {arxiv_id}")
            return None

        title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
        title = re.sub(r'\s+', ' ', title)

        published = entry.find('atom:published', ns).text
        year = published[:4]
        month = published[5:7]

        authors = []
        for author in entry.findall('atom:author', ns):
            name = author.find('atom:name', ns).text.strip()
            parts = name.rsplit(' ', 1)
            if len(parts) == 2:
                first, last = parts
                initials = ' '.join(p[0] + '.' for p in first.split())
                authors.append(f"{initials} {last}")
            else:
                authors.append(name)
        author_str = ' and '.join(authors)

        primary = entry.find('arxiv:primary_category', ns)
        category = primary.attrib.get('term', '') if primary is not None else ''

        first_author_last = authors[0].split()[-1] if authors else 'Unknown'
        key = f"{first_author_last}_{year}_arxiv"

        month_map = {
            '01':'jan','02':'feb','03':'mar','04':'apr','05':'may','06':'jun',
            '07':'jul','08':'aug','09':'sep','10':'oct','11':'nov','12':'dec'
        }

        # 按 IEEE Reference Guide v3.28.2025 §II.S 的 Preprint arXiv 格式
        arxiv_note = f"arXiv:{arxiv_id}"
        if category:
            arxiv_note += f" [{category}]"

        bibtex = (
            f"@misc{{{key},\n"
            f"  title  = {{{title}}},\n"
            f"  author = {{{author_str}}},\n"
            f"  year   = {{{year}}},\n"
            f"  month  = {month_map.get(month, month)},\n"
            f"  note   = {{{arxiv_note}}}\n"
            f"}}"
        )
        return bibtex

    except Exception as e:
        print(f"  [-] 解析 arXiv 响应时出错: {e}")
    return None

# ──────────────────────────────────────────────
# 路径收集 & 主流程
# ──────────────────────────────────────────────

def collect_pdf_paths(inputs):
    pdf_files = []
    for item in inputs:
        if os.path.isdir(item):
            found = sorted(glob.glob(os.path.join(item, '**', '*.pdf'), recursive=True))
            if not found:
                print(f"[!] 文件夹中未找到 PDF 文件: {item}")
            pdf_files.extend(found)
        elif os.path.isfile(item):
            if item.lower().endswith('.pdf'):
                pdf_files.append(item)
            else:
                print(f"[!] 跳过非 PDF 文件: {item}")
        else:
            print(f"[!] 路径不存在，已跳过: {item}")
    return pdf_files


def process_single_pdf(pdf_path):
    """
    【改动 5】全文只提取一次，逐级尝试：
      DOI(正文) → arXiv(正文) → 标题(正文 → 文件名) → Crossref → OpenAlex
    """
    text = extract_text_from_pdf(pdf_path)

    # 1. DOI
    doi = extract_doi_from_text(text)
    if doi:
        print(f"  [+] 找到 DOI: {doi}，查询 Crossref...")
        bibtex = get_bibtex_by_doi(doi)
        if bibtex:
            return bibtex, 'doi'

    # 2. arXiv
    arxiv_id = extract_arxiv_id_from_text(text)
    if arxiv_id:
        print(f"  [+] 找到 arXiv ID: {arxiv_id}，查询 arXiv API...")
        bibtex = get_bibtex_by_arxiv_id(arxiv_id)
        if bibtex:
            return bibtex, 'arxiv'

    # 3. 标题：先从正文抽，抽不到则用文件名兜底
    title = extract_title_from_text(text)
    if not title:
        title = clean_filename_as_title(pdf_path)
        if title:
            print(f"  [i] PDF 无可用文本层，改用文件名作为标题")

    if title:
        print(f"  [+] 未找到 DOI/arXiv，尝试用标题搜索：")
        print(f"      {title[:80]}{'...' if len(title) > 80 else ''}")

        # 3a. Crossref
        bibtex = get_bibtex_by_title_search(title)
        if bibtex:
            return bibtex, 'title'

        # 3b. OpenAlex 兜底
        print(f"  [i] Crossref 标题搜索未命中，尝试 OpenAlex...")
        bibtex = get_bibtex_by_openalex_title_search(title)
        if bibtex:
            return bibtex, 'openalex'

    return None, None


def fix_existing_bib(bib_path, output_path):
    """对已有 .bib 文件执行全套后处理，修复旧版生成的文件。"""
    if not os.path.exists(bib_path):
        print(f"[-] 文件不存在: {bib_path}")
        return
    with open(bib_path, 'r', encoding='utf-8') as f:
        content = f.read()
    entries = re.split(r'\n(?=@)', content.strip())
    cleaned = [postprocess(e.strip()) for e in entries if e.strip()]
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n\n'.join(cleaned) + '\n')
    print(f"[OK] 已处理 {len(cleaned)} 条文献，写入: {output_path}")


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  处理 PDF 文件夹 : python pdf2ieee.py /path/to/papers/")
        print("  处理多个 PDF    : python pdf2ieee.py a.pdf b.pdf c.pdf")
        print("  指定输出文件    : python pdf2ieee.py /path/to/papers/ -o refs.bib")
        print("  修复已有 bib    : python pdf2ieee.py --fix-bib refs.bib")
        return

    args = sys.argv[1:]
    output_path = "references.bib"
    input_args = []

    i = 0
    while i < len(args):
        if args[i] == '-o' and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        elif args[i] == '--fix-bib' and i + 1 < len(args):
            bib_input = args[i + 1]
            i += 2
            while i < len(args):
                if args[i] == '-o' and i + 1 < len(args):
                    output_path = args[i + 1]
                    i += 2
                else:
                    i += 1
            fix_existing_bib(bib_input, output_path)
            return
        else:
            input_args.append(args[i])
            i += 1

    pdf_files = collect_pdf_paths(input_args)
    if not pdf_files:
        print("[-] 没有找到任何 PDF 文件，退出。")
        return

    total = len(pdf_files)
    success_doi = 0
    success_arxiv = 0
    success_title = 0
    success_openalex = 0
    failed_files = []

    print(f"\n[*] 共找到 {total} 个 PDF，输出至: {output_path}\n")
    print("=" * 50)

    with open(output_path, 'w', encoding='utf-8') as out_f:
        for idx, pdf_path in enumerate(pdf_files, 1):
            filename = os.path.basename(pdf_path)
            print(f"[{idx}/{total}] {filename}")

            bibtex, source = process_single_pdf(pdf_path)

            if bibtex:
                bibtex = postprocess(bibtex)
                out_f.write(bibtex.strip() + "\n\n")
                if source == 'doi':
                    success_doi += 1
                    print(f"  [OK] 写入成功（DOI）\n")
                elif source == 'arxiv':
                    success_arxiv += 1
                    print(f"  [OK] 写入成功（arXiv 预印本）\n")
                elif source == 'openalex':
                    success_openalex += 1
                    print(f"  [OK] 写入成功（OpenAlex 兜底）\n")
                else:
                    success_title += 1
                    print(f"  [OK] 写入成功（Crossref 标题搜索）\n")
            else:
                failed_files.append(pdf_path)
                print(f"  [-] 未找到 DOI / arXiv / 标题匹配，已跳过\n")

    print("=" * 50)
    total_ok = success_doi + success_arxiv + success_title + success_openalex
    print(f"\n处理完成：{total_ok}/{total} 篇成功写入 {output_path}")
    print(f"  正式 DOI           ：{success_doi} 篇")
    print(f"  arXiv 预印本       ：{success_arxiv} 篇")
    print(f"  Crossref 标题反查  ：{success_title} 篇")
    print(f"  OpenAlex 兜底      ：{success_openalex} 篇")

    if failed_files:
        print(f"\n以下 {len(failed_files)} 个文件处理失败：")
        for f in failed_files:
            print(f"  - {f}")
        print("\n可能原因：")
        print("  • AAAI / NeurIPS / ICML 等会议不注册 Crossref DOI，且论文未上 arXiv")
        print("  • PDF 文本抽取不完整（扫描件或特殊字体）且未安装 OCR")
        print("  • 文件名与论文标题差异过大，模糊搜索无法命中")
        print("\n建议：")
        print("  • 扫描版 PDF 安装 OCR：pip install pytesseract pdf2image")
        print("    系统包：apt install tesseract-ocr poppler-utils")
        print("  • 手动到 DBLP / Google Scholar / Semantic Scholar 搜索标题获取 BibTeX")
        print("  • AAAI 论文可从 https://ojs.aaai.org/index.php/AAAI 页面导出")

    print("\n── 下一步 ──────────────────────────────────")
    print("1. 在 .tex 末尾添加：")
    print("     \\bibliographystyle{IEEEtran}")
    print(f"    \\bibliography{{{os.path.splitext(output_path)[0]}}}")
    print("2. 编译：pdflatex → bibtex → pdflatex → pdflatex")


if __name__ == "__main__":
    main()
