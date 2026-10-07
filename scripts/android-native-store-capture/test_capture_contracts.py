"""Native UI coordinate and CI isolation checks; never starts a host device."""
import ast
import importlib.util
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
import yaml
sys.dont_write_bytecode=True
folder=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('capture_driver',folder/'capture.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)

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

if __name__=='__main__':unittest.main()
