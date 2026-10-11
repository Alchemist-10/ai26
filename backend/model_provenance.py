"""Bind lazy ALPR initialization to the exact local files it loads, without per-frame IO."""
import hashlib
import os
from pathlib import Path
import tempfile
from importlib.metadata import version

DETECTOR_MODEL = 'yolo-v9-t-384-license-plate-end2end'
OCR_MODEL = 'global-plates-mobile-vit-v2-model'


def file_sha256(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def snapshot_model_file(source, root, role):
    """Hash the bytes being copied, publish atomically, and never overwrite a corrupt digest file."""
    source,root = Path(source),Path(root)
    root.mkdir(parents=True,exist_ok=True)
    temporary = None
    try:
        with source.open('rb') as original, tempfile.NamedTemporaryFile(dir=root,delete=False) as output:
            temporary=Path(output.name); digest=hashlib.sha256();size=0
            for chunk in iter(lambda:original.read(1024*1024),b''):
                output.write(chunk);digest.update(chunk);size+=len(chunk)
            output.flush();os.fsync(output.fileno())
        if not size: raise ValueError('Model/config file is empty')
        digest=digest.hexdigest()
        target=root/(digest+source.suffix)
        if target.exists():
            if target.stat().st_size!=size or file_sha256(target)!=digest:
                raise ValueError('Stored model/config digest verification failed')
        else:
            # Only the background inference owner initializes these models.
            temporary.replace(target)
        return target,{'role':role,'sha256':digest,'size':size,'filename':source.name}
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def verify_model_files(files):
    for path,record in files:
        if Path(path).stat().st_size!=record['size'] or file_sha256(path)!=record['sha256']:
            raise ValueError('Model/config changed during initialization')


def pipeline_components(root):
    # Explicit coverage, rather than implying that one source file covers the whole app.
    names=('inference.py','model_provenance.py','tracking.py','fusion.py','plate_format.py','processing.py','artifacts.py','cameras.py','source_catalog.py')
    return {name:file_sha256(Path(root)/name) for name in names}


def load_plate_model(root=None,cpu_threads=2,device='cpu'):
    # Imports/downloads remain lazy; missing camera sources do not provision unused models.
    import onnxruntime as ort
    from fast_alpr import ALPR
    from fast_alpr.default_ocr import DefaultOCR
    from open_image_models import create_detector
    from open_image_models.detection.core.hub import DETECTION_MODELS, download_model as detector_download
    from fast_plate_ocr.inference.hub import download_model as ocr_download

    if root is None:
        root=Path(os.environ.get('AI26_DATA_ROOT',Path(__file__).parent/'data'))/'models'
    detector_source=detector_download(DETECTOR_MODEL)
    ocr_source,config_source=ocr_download(OCR_MODEL)
    files=[snapshot_model_file(source,root,role) for source,role in
           ((detector_source,'plate_detector_weights'),(ocr_source,'ocr_weights'),(config_source,'ocr_configuration'))]
    detector_path,ocr_path,config_path=(entry[0] for entry in files)
    options=ort.SessionOptions()
    options.intra_op_num_threads=cpu_threads
    options.inter_op_num_threads=1
    providers=['CPUExecutionProvider'] if device=='cpu' else ort.get_available_providers()
    spec=DETECTION_MODELS[DETECTOR_MODEL]
    detector=create_detector(detector_path,backend=spec.backend,class_labels=spec.class_labels,
                             conf_thresh=.4,providers=providers,sess_options=options)
    # Both predict methods conform to the same interfaces used by Fast-ALPR's defaults.
    ocr=DefaultOCR(hub_ocr_model=None,model_path=ocr_path,config_path=config_path,
                   providers=providers,sess_options=options)
    model=ALPR(detector=detector,ocr=ocr)
    verify_model_files(files)
    metadata={'weight_provenance_status':'hashed_loaded_files','detector_model':DETECTOR_MODEL,'ocr_model':OCR_MODEL,
              'model_files':[entry[1] for entry in files],
              'detector_execution_providers':detector.model.get_providers(),
              'ocr_execution_providers':ocr.ocr_model.model.get_providers(),
              'onnx_intra_op_threads':cpu_threads,'onnx_inter_op_threads':1,
              'fast_alpr_version':version('fast-alpr'),'fast_plate_ocr_version':version('fast-plate-ocr'),
              'open_image_models_version':version('open-image-models'),'onnxruntime_version':version('onnxruntime')}
    return model,metadata
