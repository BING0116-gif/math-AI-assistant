import fitz,glob,os,re,datetime,json
root=r'C:\Users\HUAWEI\Desktop\高数题＋答案pdf'
out=[]
for p in sorted(glob.glob(root+r'\*.pdf')):
    d=fitz.open(p); text='\n'.join(pg.get_text() for pg in d); name=os.path.basename(p)
    nums=len(re.findall(r'(?m)^\s*\d{1,2}[．.、)]',text)); ans=len(re.findall(r'答案',text)); hints=len(re.findall(r'提示',text)); chapter='未识别'
    for pat,label in [(r'第一章|函数与极限','第一章 函数与极限'),(r'第二章|导数与微分','第二章 导数与微分'),(r'第三章|中值定理','第三章 中值定理与导数应用'),(r'第四章|不定积分','第四章 不定积分'),(r'第五章|定积分','第五章 定积分'),(r'第六章|多元函数','第六章 多元函数'),(r'第七章|无穷级数','第七章/无穷级数'),(r'第八章|微分方程','第八章 微分方程'),(r'第九章','第九章 无穷级数')]:
        if re.search(pat,name): chapter=label; break
    out.append({'name':name,'pages':len(d),'chars':len(text),'question_markers':nums,'answer_markers':ans,'hint_markers':hints,'chapter':chapter,'ocr_required':len(text)<100})
report=['# 高数题库只读解析报告','',f'> 生成时间：{datetime.datetime.now().astimezone().isoformat(timespec="seconds")}',r'> 范围：`C:\Users\HUAWEI\Desktop\高数题＋答案pdf`','> 状态：只读扫描；未写入数据库、Qdrant 或原始文件。','', '## 总览','',f'- PDF 文件：{len(out)} 个',f'- 总页数：{sum(x["pages"] for x in out)} 页',f'- 可提取文本：{sum(not x["ocr_required"] for x in out)} 个',f'- 需要 OCR/视觉解析：{sum(x["ocr_required"] for x in out)} 个',f'- 文本字符数：{sum(x["chars"] for x in out):,} 字符','', '## 文件明细','', '| 文件 | 页数 | 文本字符 | 题号标记 | 答案标记 | 提示标记 | 章节 | 处理建议 |','|---|---:|---:|---:|---:|---:|---|---|']
for x in out: report.append(f'| {x["name"]} | {x["pages"]} | {x["chars"]:,} | {x["question_markers"]} | {x["answer_markers"]} | {x["hint_markers"]} | {x["chapter"]} | {"OCR + 视觉复核" if x["ocr_required"] else "文本解析 + 公式复核"} |')
report += ['', '## 配对与风险线索','', '- 多个章节存在“自测题”和“答案与提示”成对文件，可按章节名称进行初步配对。','- 第七章与第九章文件名都涉及“无穷级数”，需要人工确认是否重复或属于不同版本。','- 文本型 PDF 的公式提取存在上下标、根号、积分符号和负号错位风险，不能直接作为最终题干。','- `4e068e81320b-cb.pdf` 文本层为空，已确认需要 OCR/视觉解析；首屏看起来是《高等数学（二）》期末考试 A 卷。','- 题号标记是解析估计值，不等于最终题目数；选择题、填空题、解答题和跨页题需要版面级切分。','', '## 建议的下一步','', '1. 对扫描型 PDF 做 OCR，并保留页码和版面坐标。','2. 对文本型 PDF 做题干/选项/答案/提示分段。','3. 建立题目与答案文件的配对关系。','4. 用题干归一化、章节、题号和答案相似度做去重候选。','5. 输出待审核 JSON；审核通过后再考虑导入数据库和向量库。','']
path='reports/高数题库只读解析报告.md'; open(path,'w',encoding='utf-8').write('\n'.join(report)); print(path); print(json.dumps(out,ensure_ascii=False,indent=2))
