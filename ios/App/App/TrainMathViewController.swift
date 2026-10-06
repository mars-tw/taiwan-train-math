import Capacitor

class TrainMathViewController: CAPBridgeViewController {
    override func capacitorDidLoad() { bridge?.registerPluginInstance(OfflineSpeechPlugin()) }
}
