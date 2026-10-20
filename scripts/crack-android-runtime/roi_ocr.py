"""Scoped derived OCR with original-pixel mapping; never supplies unrecognized tap coordinates."""
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance
import csv, hashlib, io, json, time
import math

TSV_FIELDS={'level','page_num','block_num','par_num','line_num','word_num','left','top','width','height','conf','text'}

class FlowDeadlineExceeded(RuntimeError):
    pass

class CaptionDeadlineExceeded(RuntimeError):
    pass

def caption_budget(caption,until,flow_deadline,now=None):
    now=time.monotonic() if now is None else now
    if now>=flow_deadline:raise FlowDeadlineExceeded('NATIVE_FLOW_DEADLINE_900S_EXCEEDED: '+caption)
    if now>=until:raise CaptionDeadlineExceeded('NATIVE_CAPTION_DEADLINE_EXCEEDED: '+caption)
    return min(until,flow_deadline)-now

def read_tsv(text):
    # Tesseract emits raw TSV, including bare double quotes as recognized text.
    # CSV quote handling can consume hundreds of later physical rows.
    reader=csv.DictReader(io.StringIO(text,newline=''),delimiter='\t',quoting=csv.QUOTE_NONE,quotechar=None);fields=reader.fieldnames
    if not fields or len(fields)!=len(set(fields)) or not TSV_FIELDS.issubset(fields):raise RuntimeError('OCR TSV schema invalid')
    rows=[]
    for row in reader:
        if None in row or any(value is None for value in row.values()):raise RuntimeError('OCR TSV row malformed')
        try:
            for field in TSV_FIELDS-{'conf','text'}:int(row[field])
            confidence=float(row['conf'])
            if not math.isfinite(confidence):raise ValueError('Nonfinite confidence')
        except (ValueError,TypeError) as error:raise RuntimeError('OCR TSV numeric field invalid') from error
        if row['level']=='5' and row['text'].strip() and (int(row['left'])<0 or int(row['top'])<0 or int(row['width'])<=0 or int(row['height'])<=0):raise RuntimeError('OCR word bbox invalid')
        rows.append(row)
    return fields,rows

# These rectangles limit recognition to source-defined visible UI areas. They are
# not tap locations: only a uniquely recognized text bbox can return coordinates.
REGIONS={
    '開始出擊':[(.08,.165,.395,.25)],
    '世界地圖':[(.045,.315,.205,.405)],
    '關卡出擊':[(.25,.84,.46,.98)], # Actual R4 009 caption bbox [589,956,765,1017] at 1920x1080.
    '返回':[(.045,.87,.11,.95)], # Actual R4 009 caption-only interior; exclude the rounded button border.
    'HP':[(0,0,.52,.30)], 'Lv.':[(.20,.055,.265,.12)], '等級':[(0,0,.65,.32)],
    '暫停':[(.70,0,1.0,.27)],
    '旋':[(.92,.835,.967,.925)], '斬':[(.92,.835,.967,.925)], # Source ability-button glyph interior, not the central combo caption.
    '繼續':[(.10,.35,.90,1.0)],
}

def roi_rectangles(size,caption):
    width,height=size;out=[]
    for ratios in REGIONS.get(caption,[]):
        box=[int(round(ratios[0]*width)),int(round(ratios[1]*height)),int(round(ratios[2]*width)),int(round(ratios[3]*height))]
        if not 0<=box[0]<box[2]<=width or not 0<=box[1]<box[3]<=height:raise RuntimeError('ROI outside original frame')
        out.append(box)
    return out

def map_box(box,origin,size):
    out=[box[0]+origin[0],box[1]+origin[1],box[2]+origin[0],box[3]+origin[1]]
    if not 0<=out[0]<out[2]<=size[0] or not 0<=out[1]<out[3]<=size[1]:raise RuntimeError('OCR mapped bbox outside original PNG')
    return out

def mapped_tsv(text,origin):
    fields,rows=read_tsv(text)
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=fields,delimiter='\t',lineterminator='\n',quoting=csv.QUOTE_NONE,quotechar=None);writer.writeheader()
    for row in rows:
        row['left']=str(int(row['left'])+origin[0]);row['top']=str(int(row['top'])+origin[1]);writer.writerow(row)
    return out.getvalue()

def clipped_word_tsv(text,rect):
    fields,rows=read_tsv(text);selected=[]
    for row in rows:
        if row['level']!='5':continue
        left,top,width,height=(int(row[k]) for k in ['left','top','width','height'])
        if rect[0]<=left<left+width<=rect[2] and rect[1]<=top<top+height<=rect[3]:selected.append(row)
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=fields,delimiter='\t',lineterminator='\n',quoting=csv.QUOTE_NONE,quotechar=None);writer.writeheader();writer.writerows(selected)
    return out.getvalue()

def merge_tsv(native,mapped):
    fields,rows=read_tsv(native);mapped_fields,mapped_rows=read_tsv(mapped)
    if fields!=mapped_fields:raise RuntimeError('OCR TSV schemas differ')
    # Derived OCR has its own line hierarchy. Give it a new page namespace so
    # unrelated native/ROI rows cannot become one line in label_box.
    offset=max([int(row['page_num']) for row in rows]+[0])
    for row in mapped_rows:row['page_num']=str(int(row['page_num'])+offset)
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=fields,delimiter='\t',lineterminator='\n',quoting=csv.QUOTE_NONE,quotechar=None);writer.writeheader();writer.writerows(rows+mapped_rows)
    return out.getvalue()

def find_caption(native_path,caption,remaining_seconds,ocr_runner,label_finder,output):
    native_path=Path(native_path);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    original=native_path.read_bytes();source_sha=hashlib.sha256(original).hexdigest()
    image=Image.open(io.BytesIO(original)).convert('RGB');started=time.monotonic();trials=[]
    for region_index,rect in enumerate(roi_rectangles(image.size,caption)):
        raw=image.crop(tuple(rect));variants=[('contrast',ImageEnhance.Contrast(ImageOps.autocontrast(ImageOps.grayscale(raw))).enhance(2.0)),('raw',raw)]
        if caption=='返回':variants.append(('inverse',ImageOps.invert(ImageOps.grayscale(raw))))
        for variant,derived in variants:
            if derived.size != raw.size:raise RuntimeError('Unexpected OCR resize; native-coordinate proof invalid')
            for psm in [7,6]:
                prefix=native_path.stem+'-roi-'+str(region_index)+'-'+variant+'-psm'+str(psm)+'-'+hashlib.sha256(caption.encode()).hexdigest()[:8]
                path=output/(prefix+'.png');derived.save(path)
                budget=remaining_seconds-(time.monotonic()-started)
                stdout,stderr,receipt=ocr_runner(['tesseract',str(path),'stdout','-l','chi_tra+eng','--psm',str(psm),'tsv'],budget)
                (output/(prefix+'.stdout.tsv')).write_bytes(stdout);(output/(prefix+'.stderr.txt')).write_bytes(stderr)
                receipt.update(caption=caption,psm=psm,variant=variant,originalFrame=str(native_path),originalSha256=source_sha,
                    originalSize=list(image.size),cropRect=rect,resizeApplied=False,derivedSha256=hashlib.sha256(path.read_bytes()).hexdigest())
                text=stdout.decode('utf-8','replace');local_box=None
                if not receipt['timedOut'] and receipt['exitCode']==0:
                    local_box=label_finder(text,caption)
                if local_box:
                    if not 0<=local_box[0]<local_box[2]<=derived.width or not 0<=local_box[1]<local_box[3]<=derived.height:raise RuntimeError('OCR local bbox outside derived crop')
                    native_box=map_box(local_box,rect[:2],image.size);receipt.update(recognized=True,localOCRBox=local_box,nativeOCRBox=native_box)
                    caption_rows=label_finder(text,caption,contributing_rows=True)
                    if not caption_rows:raise RuntimeError('Recognized caption has no contributing word rows')
                    fields,_=read_tsv(text);selected=io.StringIO()
                    writer=csv.DictWriter(selected,fieldnames=fields,delimiter='\t',lineterminator='\n',quoting=csv.QUOTE_NONE,quotechar=None);writer.writeheader();writer.writerows(caption_rows)
                    native_caption=mapped_tsv(selected.getvalue(),rect[:2]);native_full=mapped_tsv(text,rect[:2])
                    if label_finder(native_caption,caption)!=native_box:raise RuntimeError('Mapped caption contributors do not reproduce recognized native bbox')
                    full_path=output/(prefix+'.native-full.tsv');caption_path=output/(prefix+'.native-caption.tsv')
                    full_path.write_text(native_full,encoding='utf-8');caption_path.write_text(native_caption,encoding='utf-8')
                    receipt.update(nativeFullTSVFile=str(full_path),nativeFullTSVSha256=hashlib.sha256(full_path.read_bytes()).hexdigest(),
                        nativeCaptionTSVFile=str(caption_path),nativeCaptionTSVSha256=hashlib.sha256(caption_path.read_bytes()).hexdigest(),
                        contributedWordRows=len(caption_rows),onlyCurrentCaptionContributorsMerged=True)
                else:receipt['recognized']=False
                (output/(prefix+'.receipt.json')).write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');trials.append(receipt)
                if local_box:
                    if hashlib.sha256(native_path.read_bytes()).hexdigest()!=source_sha:raise RuntimeError('Original native PNG changed during recognition')
                    return {'nativeBox':native_box,'nativeMappedTSV':native_full,'nativeCaptionTSV':native_caption,'caption':caption,'trials':trials,'originalSha256':source_sha,'textRequiredForCoordinates':True}
    if hashlib.sha256(native_path.read_bytes()).hexdigest()!=source_sha:raise RuntimeError('Original native PNG changed during recognition')
    return {'nativeBox':None,'caption':caption,'trials':trials,'originalSha256':source_sha,'textRequiredForCoordinates':True}
