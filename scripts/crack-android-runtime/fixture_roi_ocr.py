"""Fixed original R3 menu and R4 map fixtures, before any APK fetch/emulator session."""
from pathlib import Path
import hashlib,io,json,os,subprocess,zipfile
from run_probe import bounded_native_ocr,label_box
from roi_ocr import find_caption,read_tsv,map_box
REPO='mars-tw/taiwan-train-math';ARTIFACT=11725738378;RUN=38201436078
HEAD='acf5235e7e8331260b6a4ce0844c4ff0bd27cea1'
SIZE=64669164;ZIP_SHA='189c1a83f2df932f3b65a801aa8177d7a8a1b7c8bc9d81c366279f4ef8e62a12'
IMAGE_SHA='3732d03d4e1ac5d71a5ce6ef817e05f030facffb24395def8f240ea34a6a835b'
MAP_ARTIFACT=11726623282;MAP_RUN=38204384086;MAP_HEAD='ec2733515572422dad66a93762d9bf32b960202a'
MAP_SIZE=20088721;MAP_ZIP_SHA='9b61ae31c76440992eb74b0244f72f36fca9d1eaf29b3dceeff8214f5004b874'
MAP_IMAGE_SHA='4a2458651bf355d4c032f872ab2d29e29882581924bde5943b3855a56964cb9f'
MAP_TSV_SHA='e4f47efc01bdeded06942b1c873d8b89ed18824254a947ab22971268a3ad0203'
def get(resource):
    r=subprocess.run(['gh','api',resource,'--method','GET'],capture_output=True,timeout=180)
    if r.returncode:raise RuntimeError('Fixed official fixture GET failed; provideroutputwithheld')
    return r.stdout
def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!=REPO or os.environ.get('GITHUB_REF')!='refs/heads/codex/ashes-simulator-recording':raise RuntimeError('Exact QAbranch fixture only')
    out=Path(os.environ['GITHUB_WORKSPACE'])/'output/crack-roi-fixture';out.mkdir(parents=True,exist_ok=True)
    report={'status':'PREPARING_EXACT_ORIGINAL_ROI_FIXTURE','actualNativeBoots':0,'gameExecuted':False,'APKChanged':False,
        'actualReturnCaptionFixtureVerified':False,'actualReturnNavigationVerified':False}
    try:
        meta=json.loads(get(f'repos/{REPO}/actions/artifacts/{ARTIFACT}'))
        assert meta['id']==ARTIFACT and meta['name']==f'crack-code2-android-runtime-{RUN}' and not meta['expired'] and meta['size_in_bytes']==SIZE
        assert meta['workflow_run']['id']==RUN and meta['workflow_run']['head_sha']==HEAD
        blob=get(f'repos/{REPO}/actions/artifacts/{ARTIFACT}/zip');assert len(blob)==SIZE and hashlib.sha256(blob).hexdigest()==ZIP_SHA
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            matches=[n for n in z.namelist() if n=='native-frames/024-cold-title-wait.png'];assert len(matches)==1
            raw=z.read(matches[0]);assert len(raw)==3171204 and hashlib.sha256(raw).hexdigest()==IMAGE_SHA
        image=out/'024-original-native.png';image.write_bytes(raw)
        results=[]
        for caption in ['開始出擊','世界地圖']:
            r=find_caption(image,caption,180,bounded_native_ocr,label_box,out/'derived');results.append(r)
            if not r['nativeBox']:raise RuntimeError('Actual fixed original ROI caption not recognized: '+caption)
        meta=json.loads(get(f'repos/{REPO}/actions/artifacts/{MAP_ARTIFACT}'))
        assert meta['id']==MAP_ARTIFACT and meta['name']==f'crack-code2-android-runtime-{MAP_RUN}' and not meta['expired'] and meta['size_in_bytes']==MAP_SIZE
        assert meta['workflow_run']['id']==MAP_RUN and meta['workflow_run']['head_sha']==MAP_HEAD
        blob=get(f'repos/{REPO}/actions/artifacts/{MAP_ARTIFACT}/zip');assert len(blob)==MAP_SIZE and hashlib.sha256(blob).hexdigest()==MAP_ZIP_SHA
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            assert z.namelist().count('native-frames/009-world-map-ready.png')==1 and z.namelist().count('native-frames/009-world-map-ready.tsv')==1
            map_raw=z.read('native-frames/009-world-map-ready.png');tsv_raw=z.read('native-frames/009-world-map-ready.tsv')
            assert len(map_raw)==2293575 and hashlib.sha256(map_raw).hexdigest()==MAP_IMAGE_SHA
            assert len(tsv_raw)==15483 and hashlib.sha256(tsv_raw).hexdigest()==MAP_TSV_SHA
        map_image=out/'009-original-world-map.png';map_image.write_bytes(map_raw)
        (out/'009-original-world-map.tsv').write_bytes(tsv_raw)
        text=tsv_raw.decode('utf-8');rows=read_tsv(text)[1]
        original_map_box=label_box(text,'關卡出擊')
        assert len(rows)==432 and original_map_box==[589,956,765,1017]
        map_box(original_map_box,[0,0],(1920,1080))
        for caption in ['關卡出擊','返回']:
            r=find_caption(map_image,caption,180,bounded_native_ocr,label_box,out/'derived');results.append(r)
            if not r['nativeBox']:raise RuntimeError('Actual fixed original map ROI caption not recognized: '+caption)
        report.update(status='ACTUAL_ORIGINAL_MENU_AND_MAP_ROI_TEXT_AND_COORDINATES_VERIFIED',artifactId=ARTIFACT,originalImageSha256=IMAGE_SHA,results=results,
            fixedMapArtifactId=MAP_ARTIFACT,fixedMapOriginalSha256=MAP_IMAGE_SHA,fixedMapOriginalTSVSha256=MAP_TSV_SHA,
            actualSavedTSVRegression={'quoting':'QUOTE_NONE','rows':len(rows),'nativeBox':original_map_box,'recognizerRerun':False},
            onlyVerifiedActualCaptions=['開始出擊','世界地圖','關卡出擊','返回'],actualReturnCaptionFixtureVerified=True,actualReturnNavigationVerified=False,
            backOrHudActualVerified=False,originalPngModified=False,recognizerEnvironment='Official Ubuntu apt Tesseract chi_tra+eng, isolated childOMP1')
    except Exception as error:
        report.update(status='ACTUAL_ROI_FIXTURE_HOLD',errorType=type(error).__name__,error=str(error)[:1000]);raise
    finally:(out/'fixture-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
