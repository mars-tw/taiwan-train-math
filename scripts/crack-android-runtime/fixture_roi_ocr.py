"""Fixed R3 menu, R4 map and source-bound R6 battle fixtures; no game is executed."""
from pathlib import Path
import hashlib,io,json,os,subprocess,zipfile
from run_probe import bounded_native_ocr,label_box,exact_word_box,source_hud_boxes,source_skill_box,SOURCE_CAPTION_CONTRACT
from roi_ocr import find_caption,read_tsv,map_box,roi_rectangles,clipped_word_tsv
REPO='mars-tw/taiwan-train-math';ARTIFACT=11725738378;RUN=38201436078
HEAD='acf5235e7e8331260b6a4ce0844c4ff0bd27cea1'
SIZE=64669164;ZIP_SHA='189c1a83f2df932f3b65a801aa8177d7a8a1b7c8bc9d81c366279f4ef8e62a12'
IMAGE_SHA='3732d03d4e1ac5d71a5ce6ef817e05f030facffb24395def8f240ea34a6a835b'
MAP_ARTIFACT=11726623282;MAP_RUN=38204384086;MAP_HEAD='ec2733515572422dad66a93762d9bf32b960202a'
MAP_SIZE=20088721;MAP_ZIP_SHA='9b61ae31c76440992eb74b0244f72f36fca9d1eaf29b3dceeff8214f5004b874'
MAP_IMAGE_SHA='4a2458651bf355d4c032f872ab2d29e29882581924bde5943b3855a56964cb9f'
MAP_TSV_SHA='e4f47efc01bdeded06942b1c873d8b89ed18824254a947ab22971268a3ad0203'
BATTLE_ARTIFACT=11727489773;BATTLE_RUN=38207242365;BATTLE_HEAD='b07c9c3f41313cbed8609080a5642702aa7c3222'
BATTLE_SIZE=55211265;BATTLE_ZIP_SHA='a308aabb65651e2880db4ab323a61c2176494e457e050aa68176b14431fad335'
BATTLE_IMAGE_SHA='65b07b8dc247d26eb5d5767e0df8cf01a3327fadb1f0594d58f074325cc94e70'
BATTLE_TSV_SHA='5bfff177670ca2c0c70434baaae3a77273fb87de02a6e13bcaf04ca522721e5f'
def get(resource):
    r=subprocess.run(['gh','api',resource,'--method','GET'],capture_output=True,timeout=180)
    if r.returncode:raise RuntimeError('Fixed official fixture GET failed; provideroutputwithheld')
    return r.stdout
def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!=REPO or os.environ.get('GITHUB_REF')!='refs/heads/codex/crack2-kvm-qa-20261013-r12':raise RuntimeError('Exact QAbranch fixture only')
    out=Path(os.environ['GITHUB_WORKSPACE'])/'output/crack-roi-fixture';out.mkdir(parents=True,exist_ok=True)
    report={'status':'PREPARING_EXACT_ORIGINAL_ROI_FIXTURE','actualNativeBoots':0,'gameExecuted':False,'APKChanged':False,
        'actualReturnCaptionFixtureVerified':False,'actualReturnNavigationVerified':False,
        'actualBattleHUDCaptionFixtureVerified':False,'actualSkillRotationCaptionFixtureVerified':False,
        'actualSkillSlashCaptionFixtureVerified':False,'actualSkillActionVerified':False}
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
        report.update(results=results,onlyVerifiedActualCaptions=['開始出擊','世界地圖','關卡出擊','返回'],actualReturnCaptionFixtureVerified=True)
        meta=json.loads(get(f'repos/{REPO}/actions/artifacts/{BATTLE_ARTIFACT}'))
        assert meta['id']==BATTLE_ARTIFACT and meta['name']==f'crack-code2-android-runtime-{BATTLE_RUN}' and not meta['expired'] and meta['size_in_bytes']==BATTLE_SIZE
        assert meta['workflow_run']['id']==BATTLE_RUN and meta['workflow_run']['head_sha']==BATTLE_HEAD
        blob=get(f'repos/{REPO}/actions/artifacts/{BATTLE_ARTIFACT}/zip');assert len(blob)==BATTLE_SIZE and hashlib.sha256(blob).hexdigest()==BATTLE_ZIP_SHA
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            assert z.namelist().count('native-frames/016-after-visible-start.png')==1 and z.namelist().count('native-frames/016-after-visible-start.tsv')==1
            battle_raw=z.read('native-frames/016-after-visible-start.png');battle_saved_tsv=z.read('native-frames/016-after-visible-start.tsv')
            assert len(battle_raw)==3822515 and hashlib.sha256(battle_raw).hexdigest()==BATTLE_IMAGE_SHA
            assert len(battle_saved_tsv)==14704 and hashlib.sha256(battle_saved_tsv).hexdigest()==BATTLE_TSV_SHA
        battle_image=out/'016-original-battle.png';battle_image.write_bytes(battle_raw)
        (out/'016-original-battle.saved.tsv').write_bytes(battle_saved_tsv)
        saved_hud=source_hud_boxes(battle_saved_tsv.decode('utf-8'),(1920,1080))
        assert saved_hud=={'hpBox':[108,48,167,105],'levelBox':[419,78,476,103],'levelPrefix':'Lv.','pauseBox':[1811,93,1875,124],'complete':True}
        assert source_skill_box(battle_saved_tsv.decode('utf-8'),(1920,1080)) is None # Central combo 斬 is not the ability button.
        stdout,stderr,receipt=bounded_native_ocr(['tesseract',str(battle_image),'stdout','-l','chi_tra+eng','--psm','11','tsv'],180)
        (out/'016-original-battle.fresh.stdout.tsv').write_bytes(stdout);(out/'016-original-battle.fresh.stderr.txt').write_bytes(stderr)
        receipt.update(originalFrame=str(battle_image),originalSha256=BATTLE_IMAGE_SHA,sourceCaptionContract=SOURCE_CAPTION_CONTRACT)
        (out/'016-original-battle.fresh.receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if receipt['timedOut'] or receipt['exitCode']!=0:raise RuntimeError('Actual fixed battle full-frame OCR child failed')
        fresh_text=stdout.decode('utf-8');fresh_hud=source_hud_boxes(fresh_text,(1920,1080))
        if not fresh_hud['complete'] or fresh_hud['levelPrefix']!='Lv.':raise RuntimeError('Actual fixed battle HP/Lv./pause captions not recognized')
        if not exact_word_box(clipped_word_tsv(fresh_text,roi_rectangles((1920,1080),'Lv.')[0]),'Lv.1'):raise RuntimeError('Actual fixed battle source level label Lv.1 not recognized')
        report.update(actualBattleHUDCaptionFixtureVerified=True,battleFreshHUDCaptionProof=fresh_hud,
            onlyVerifiedActualCaptions=['開始出擊','世界地圖','關卡出擊','返回','HP','Lv.1','暫停'])
        r=find_caption(battle_image,'旋',180,bounded_native_ocr,exact_word_box,out/'derived');results.append(r)
        if not r['nativeBox']:raise RuntimeError('Actual fixed original source ability-button 旋 glyph not recognized')
        report.update(status='ACTUAL_ORIGINAL_MENU_MAP_AND_SOURCE_BATTLE_CAPTIONS_VERIFIED',artifactId=ARTIFACT,originalImageSha256=IMAGE_SHA,results=results,
            fixedMapArtifactId=MAP_ARTIFACT,fixedMapOriginalSha256=MAP_IMAGE_SHA,fixedMapOriginalTSVSha256=MAP_TSV_SHA,
            actualSavedTSVRegression={'quoting':'QUOTE_NONE','rows':len(rows),'nativeBox':original_map_box,'recognizerRerun':False},
            fixedBattleArtifactId=BATTLE_ARTIFACT,fixedBattleOriginalSha256=BATTLE_IMAGE_SHA,fixedBattleOriginalTSVSha256=BATTLE_TSV_SHA,
            battleSavedHUDRegression=saved_hud,battleFreshHUDCaptionProof=fresh_hud,sourceCaptionContract=SOURCE_CAPTION_CONTRACT,
            onlyVerifiedActualCaptions=['開始出擊','世界地圖','關卡出擊','返回','HP','Lv.1','暫停','旋'],actualReturnCaptionFixtureVerified=True,actualReturnNavigationVerified=False,
            actualBattleHUDCaptionFixtureVerified=True,actualSkillRotationCaptionFixtureVerified=True,actualSkillSlashCaptionFixtureVerified=False,actualSkillActionVerified=False,
            backOrHudActualVerified=False,originalPngModified=False,recognizerEnvironment='Official Ubuntu apt Tesseract chi_tra+eng, isolated childOMP1')
    except Exception as error:
        report.update(status='ACTUAL_ROI_FIXTURE_HOLD',errorType=type(error).__name__,error=str(error)[:1000]);raise
    finally:(out/'fixture-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
