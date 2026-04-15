import re
import requests
import PyPDF2
import sys
import os
import glob
import xml.etree.ElementTree as ET

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
    """删除 url/doi/issn/publisher 字段，防止出现 [Online]. Available: ..."""
    drop_fields = ['url', 'doi', 'issn', 'publisher']
    for field in drop_fields:
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
    """依次执行：格式美化 → 删除冗余字段 → IEEE 期刊缩写 → 专有名词大写保护"""
    bibtex = prettify_bibtex(bibtex)
    bibtex = strip_redundant_fields(bibtex)
    bibtex = apply_ieee_journal_macros(bibtex)
    bibtex = protect_title_caps(bibtex)
    return bibtex

# ──────────────────────────────────────────────
# DOI 提取 & Crossref 查询
# ──────────────────────────────────────────────

def extract_doi_from_pdf(pdf_path):
    doi_pattern = re.compile(r'\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b')
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            num_pages = min(2, len(reader.pages))
            for i in range(num_pages):
                text = reader.pages[i].extract_text()
                if text:
                    matches = doi_pattern.findall(text)
                    if matches:
                        doi = matches[0].rstrip('.)]')
                        if '10.48550' not in doi:
                            return doi
    except Exception as e:
        print(f"  [-] 读取 PDF 时发生错误: {e}")
    return None


def get_bibtex_by_doi(doi):
    url = f"https://api.crossref.org/works/{doi}/transform/application/x-bibtex"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            bibtex = response.content.decode('utf-8')
            bibtex = bibtex.replace('\u2013', '--').replace('\u2014', '--')
            return bibtex
        elif response.status_code == 404:
            print(f"  [-] Crossref 未找到该 DOI: {doi}")
        else:
            print(f"  [-] 请求失败，状态码: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"  [-] 网络请求错误: {e}")
    return None

# ──────────────────────────────────────────────
# arXiv ID 提取 & API 查询
# ──────────────────────────────────────────────

def extract_arxiv_id_from_pdf(pdf_path):
    arxiv_pattern = re.compile(
        r'(?:arXiv[:\s]+)?(\d{4}\.\d{4,5}(?:v\d+)?)',
        re.IGNORECASE
    )
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            num_pages = min(2, len(reader.pages))
            for i in range(num_pages):
                text = reader.pages[i].extract_text()
                if text:
                    matches = arxiv_pattern.findall(text)
                    if matches:
                        arxiv_id = re.sub(r'v\d+$', '', matches[0])
                        return arxiv_id
    except Exception as e:
        print(f"  [-] 读取 PDF 时发生错误: {e}")
    return None


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

        bibtex = (
            f"@misc{{{key},\n"
            f"  title         = {{{title}}},\n"
            f"  author        = {{{author_str}}},\n"
            f"  year          = {{{year}}},\n"
            f"  month         = {month_map.get(month, month)},\n"
            f"  eprint        = {{{arxiv_id}}},\n"
            f"  archivePrefix = {{arXiv}},\n"
            f"  primaryClass  = {{{category}}}\n"
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
    doi = extract_doi_from_pdf(pdf_path)
    if doi:
        print(f"  [+] 找到 DOI: {doi}，查询 Crossref...")
        bibtex = get_bibtex_by_doi(doi)
        if bibtex:
            return bibtex, 'doi'

    arxiv_id = extract_arxiv_id_from_pdf(pdf_path)
    if arxiv_id:
        print(f"  [+] 找到 arXiv ID: {arxiv_id}，查询 arXiv API...")
        bibtex = get_bibtex_by_arxiv_id(arxiv_id)
        if bibtex:
            return bibtex, 'arxiv'

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
                    print(f"  [OK] 写入成功（正式期刊）\n")
                else:
                    success_arxiv += 1
                    print(f"  [OK] 写入成功（arXiv 预印本）\n")
            else:
                failed_files.append(pdf_path)
                print(f"  [-] 未找到 DOI 或 arXiv ID，已跳过\n")

    print("=" * 50)
    total_ok = success_doi + success_arxiv
    print(f"\n处理完成：{total_ok}/{total} 篇成功写入 {output_path}")
    print(f"  其中正式期刊（DOI）：{success_doi} 篇")
    print(f"  其中 arXiv 预印本  ：{success_arxiv} 篇")

    if failed_files:
        print(f"\n以下 {len(failed_files)} 个文件处理失败：")
        for f in failed_files:
            print(f"  - {f}")
        print("\n建议：对上述文件手动在 Google Scholar 搜索标题获取 BibTeX。")

    print("\n── 下一步 ──────────────────────────────────")
    print("1. 在 .tex 末尾添加：")
    print("     \\bibliographystyle{IEEEtran}")
    print(f"    \\bibliography{{{os.path.splitext(output_path)[0]}}}")
    print("2. 编译：pdflatex → bibtex → pdflatex → pdflatex")


if __name__ == "__main__":
    main()
