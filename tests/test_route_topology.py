"""Session-held-out route-time fitting stays empirical and review-only."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE_PATH = Path(__file__).parents[1] / "evaluation" / "route_topology.py"
spec = importlib.util.spec_from_file_location("route_topology", MODULE_PATH)
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)


def record(index, session, split, traversed, elapsed, edge=("CAM-01", "CAM-02"), calibrated=True):
    return {"record_id":f"r{index}","session_id":session,"from_camera":edge[0],"to_camera":edge[1],
            "elapsed_seconds":elapsed,"traversed":traversed,"split":split,
            "coordinates_validated":calibrated,"clocks_synchronized":calibrated}


class RouteTopologyTests(unittest.TestCase):
    def setUp(self):
        self.rows=[record(i,f"train-{i}","train",True,elapsed)
                   for i,elapsed in enumerate((60,70,80,90,100))]
        self.rows += [record(10,"train-negative-a","train",False,25),
                      record(11,"train-negative-b","train",False,200),
                      record(20,"test-positive","test",True,75),
                      record(21,"test-negative-false","test",False,80),
                      record(22,"test-negative-outside","test",False,15),
                      record(23,"test-unmodeled-negative","test",False,45,edge=("CAM-03","CAM-04")),
                      record(24,"test-unmodeled-positive","test",True,90,edge=("CAM-03","CAM-04"))]

    def test_learns_directed_empirical_window_and_scores_held_out_negatives(self):
        result=route.fit_and_evaluate(self.rows,"a"*64)
        edge=result['directed_edges'][0]
        self.assertEqual((edge['from_camera'],edge['to_camera']),('CAM-01','CAM-02'))
        self.assertEqual(edge['training_positive_samples'],5)
        self.assertEqual(edge['training_negative_samples'],2)
        metrics=result['held_out_metrics']
        self.assertEqual((metrics['tp'],metrics['fp'],metrics['tn'],metrics['fn']),(1,1,2,1))
        self.assertEqual(metrics['positive_test_denominator'],2)
        self.assertEqual(metrics['negative_test_denominator'],3)
        self.assertEqual(metrics['unmodeled_positive'],1)
        self.assertFalse(result['identity_linking_enabled'])
        self.assertFalse(result['production_constraints_written'])

    def test_refuses_session_leakage_unvalidated_clocks_and_weak_training(self):
        leaking=self.rows+[record(30,"train-0","test",True,75)]
        with self.assertRaises(route.RouteDataError): route.fit_and_evaluate(leaking,"a"*64)
        uncalibrated=[{**row,"clocks_synchronized":False} for row in self.rows]
        with self.assertRaises(route.RouteDataError): route.fit_and_evaluate(uncalibrated,"a"*64)
        weak=[row for row in self.rows if row['record_id']!='r4']
        with self.assertRaises(route.RouteDataError): route.fit_and_evaluate(weak,"a"*64)

    def test_loader_rejects_correlated_repeated_edge_samples_in_one_session(self):
        duplicate=[record(1,'same-session','train',True,70),
                   record(2,'same-session','train',True,72)]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'repeats.jsonl'
            path.write_text(''.join(json.dumps(row)+'\n' for row in duplicate))
            with self.assertRaises(route.RouteDataError): route.load_records(path)

    def test_jsonl_loader_hashes_source_and_rejects_mixed_session_splits(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'transitions.jsonl'
            path.write_text(''.join(json.dumps(row)+'\n' for row in self.rows))
            loaded,digest=route.load_records(path)
            self.assertEqual(len(loaded),len(self.rows))
            self.assertEqual(len(digest),64)
            path.write_text(json.dumps(record(1,'same-session','train',True,70))+'\n'+
                            json.dumps(record(2,'same-session','test',True,70))+'\n')
            with self.assertRaises(route.RouteDataError): route.load_records(path)

    def test_cli_runner_writes_no_clobber_review_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);inputs=root/'transitions.jsonl';output=root/'candidate.json'
            inputs.write_text(''.join(json.dumps(row)+'\n' for row in self.rows))
            written=route.run(inputs,output)
            result=json.loads(written.read_text())
            self.assertEqual(result['status'],'offline_review_candidate')
            self.assertEqual(result['data_sha256'],route._hash(inputs))
            with self.assertRaises(FileExistsError): route.run(inputs,output)


if __name__ == "__main__": unittest.main()
