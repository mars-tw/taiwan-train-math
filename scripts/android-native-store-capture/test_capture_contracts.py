"""Native UI coordinate and CI isolation checks; never starts a host device."""
import ast
import importlib.util
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import yaml
sys.dont_write_bytecode=True
folder=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('capture_driver',folder/'capture.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
spec2=importlib.util.spec_from_file_location('device_configuration',folder/'device_config.py');device=importlib.util.module_from_spec(spec2);spec2.loader.exec_module(device)

class Contracts(unittest.TestCase):
 def node(self,**change):
  return {'package':'tw.test.app','clickable':'true','enabled':'true','text':'略過','bounds':'[10,20][110,70]',**change}
 def test_point_is_measured_native_rect_center(self):
  target=driver.observed_target([self.node()],[r'^略過$'],1080,1920,'tw.test.app')
  self.assertEqual(target[2],[10,20,110,70]);self.assertEqual(target[3],[60,45])
 def test_no_guessed_point_for_missing_control(self):
  self.assertIsNone(driver.observed_target([self.node(text='其他控制')],[r'^略過$'],1080,1920,'tw.test.app'))
 def test_other_package_disabled_nonclickable_and_out_of_frame_rejected(self):
  for change in [{'package':'com.android.systemui'},{'enabled':'false'},{'clickable':'false'},{'bounds':'[1000,20][2000,70]'},{'bounds':'[-10,20][110,70]'},{'bounds':'[10,20][10,70]'}]:
   self.assertIsNone(driver.observed_target([self.node(**change)],[r'^略過$'],1080,1920,'tw.test.app'))
 def test_small_actual_button_preferred_over_merged_container(self):
  target=driver.observed_target([self.node(bounds='[0,0][1080,1920]'),self.node()],[r'^略過$'],1080,1920,'tw.test.app')
  self.assertEqual(target[3],[60,45])
 def test_each_helper_parses(self):
  for file in folder.glob('*.py'):ast.parse(file.read_text(encoding='utf-8'))
 def test_driver_refuses_host_environment_before_any_native_command(self):
  args=['capture.py','--project','web-card-game-skill','--family','phone','--input','unused','--output','unused','--avd','unused']
  with patch.object(sys,'argv',args),patch.dict(driver.os.environ,{'GITHUB_ACTIONS':'false'}),patch.object(driver,'run',side_effect=AssertionError('No host adb may execute')):
   with self.assertRaisesRegex(RuntimeError,'only in the owned GitHub CI'):driver.main()
 def test_workflow_uses_only_own_dispatch_and_max3_without_cancel(self):
  file=folder.parents[1]/'.github/workflows/android-native-store-capture.yml';data=yaml.safe_load(file.read_text())
  self.assertEqual(list((data.get('on') or data.get(True))),['workflow_dispatch'])
  self.assertFalse(data['concurrency']['cancel-in-progress'])
  for job in ['fetch','capture']:self.assertEqual(data['jobs'][job]['strategy']['max-parallel'],3)
 def test_capture_job_has_readonly_tokens_no_signer_or_store_secrets(self):
  data=yaml.safe_load((folder.parents[1]/'.github/workflows/android-native-store-capture.yml').read_text());job=data['jobs']['capture'];encoded=str(job)
  self.assertEqual(job['permissions'],{'contents':'read','actions':'read'})
  for forbidden in ['GH_TOKEN','APPLE','GOOGLE','keystore','secrets.']:
   self.assertNotIn(forbidden,encoded)
  self.assertIn('disable-animations',encoded);self.assertIn('false',encoded.lower())
 def test_runner_context_not_used_in_job_env_before_runner_is_assigned(self):
  data=yaml.safe_load((folder.parents[1]/'.github/workflows/android-native-store-capture.yml').read_text())
  for job in data['jobs'].values():self.assertNotIn('runner.',str(job.get('env',{})))
 def test_actual_runner_standard_avd_root_sets_tablet_dimensions_without_touching_other_avds(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);home=root/'fresh-ci-home';avds=home/'.android/avd';name='NativeCaptureTablet_123_tower';target=avds/(name+'.avd')/'config.ini';target.parent.mkdir(parents=True);target.write_text('hw.lcd.width=2560\nhw.lcd.height=1800\n')
   other=avds/'UntouchedUserDevice.avd/config.ini';other.parent.mkdir();other.write_text('untouched')
   device.configure(name,'tablet',avds,root/'runner-temp',home)
   self.assertIn('hw.lcd.width=1200',target.read_text());self.assertIn('hw.lcd.height=1920',target.read_text());self.assertEqual(other.read_text(),'untouched')
   with self.assertRaises(ValueError):device.configure('ShopeeDevice','tablet',avds,root/'runner-temp',home)
 def test_actual_card_android_accessibility_label_is_supported(self):
  node=self.node(text='略過教學')
  self.assertIsNotNone(driver.observed_target([node],[driver.ACTIONS['web-card-game-skill'][0]],1080,1920,'tw.test.app'))
 def test_controls_present_while_real_models_loading_are_not_ready_gameplay(self):
  nodes=[self.node(text='準備出發'),self.node(text='正在準備駕駛艙　載入 Blender 模型與貼圖')]
  self.assertTrue(driver.observed_loading(nodes,'tw.test.app'))
  self.assertFalse(driver.observed_loading([self.node(text='準備出發')],'tw.test.app'))
  self.assertTrue(driver.observed_loading([self.node(text='準備戰場')],'tw.test.app'))
 def test_observed_current_start_labels_match_signed_apps(self):
  for project,label in [('ashes-convoy','開始出勤'),('storm-apocalypse','確認屠夫老闆娘'),('pixel-idle-farm-skill','把農場接回來')]:
   self.assertIsNotNone(driver.observed_target([self.node(text=label)],[driver.ACTIONS[project][0]],1080,1920,'tw.test.app'))

if __name__=='__main__':unittest.main()
