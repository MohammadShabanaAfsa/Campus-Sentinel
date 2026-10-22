"""
FacePoseAnalyzer — wraps MediaPipe Face Mesh + Pose to extract per-person
signals from a cropped person region: eye-aspect-ratio (EAR), mouth-aspect-
ratio (MAR), and head/body orientation. These feed the sleeping/talking/
engagement analyzers.

MediaPipe solution objects are not safe to share across concurrent frames,
but each camera is processed in its own dedicated thread (see
ai_engine.vision.stream_manager), so one instance per camera is safe.
"""
from typing import Dict, Optional
import numpy as np
from loguru import logger

# Standard MediaPipe Face Mesh 468-point landmark indices.
# Each eye set is ordered [corner, top1, top2, corner, bottom1, bottom2]
# following the Soukupova & Cech eye-aspect-ratio formulation.
_LEFT_EYE = [362, 385, 387, 263, 373, 380]
_RIGHT_EYE = [33, 160, 158, 133, 153, 144]
_MOUTH_LEFT, _MOUTH_RIGHT, _MOUTH_TOP, _MOUTH_BOTTOM = 61, 291, 13, 14
_NOSE_TIP = 1

# MediaPipe Pose (BlazePose) 33-point landmark indices.
_POSE_NOSE = 0
_POSE_LEFT_SHOULDER = 11
_POSE_RIGHT_SHOULDER = 12


class FacePoseAnalyzer:
    """Per-camera singleton wrapping MediaPipe Face Mesh + Pose."""

    _instances: Dict[str, "FacePoseAnalyzer"] = {}

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self._face_mesh = None
        self._pose = None
        self._hands = None
        self._load()

    @classmethod
    def get_instance(cls, camera_id: str) -> "FacePoseAnalyzer":
        if camera_id not in cls._instances:
            cls._instances[camera_id] = cls(camera_id=camera_id)
        return cls._instances[camera_id]

    def _load(self):
        try:
            import mediapipe as mp
            self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=True,  # each call is an independent crop, not a video stream
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.5,
            )
            self._pose = mp.solutions.pose.Pose(
                static_image_mode=True,
                model_complexity=0,  # lite model — this runs per-person, per-frame
                min_detection_confidence=0.5,
            )
            logger.info(f"FacePoseAnalyzer[{self.camera_id}]: MediaPipe Face Mesh + Pose loaded")
            try:
                self._hands=mp.solutions.hands.Hands(static_image_mode=True,max_num_hands=2,min_detection_confidence=.6)
            except Exception as error:
                logger.warning(f'Hand landmark fallback unavailable: {type(error).__name__}')
        except Exception as e:
            logger.error(f"FacePoseAnalyzer[{self.camera_id}]: failed to load MediaPipe models: {e}")
            self._face_mesh = None
            self._pose = None

    def analyze_crop(self, crop: np.ndarray) -> Dict:
        """
        Run Face Mesh + Pose on a single person's cropped region.
        Returns a dict of signals; any that couldn't be computed are None.
        """
        result = {
            "face_detected": False, "ear": None, "mar": None,
            "pose_detected": False, "head_down": None, "facing_camera": None,
            "mouth_center": None, "wrists": {}, "elbows": {}, "shoulders": {},
            "landmark_visibility": {},
            "wrist_sources": {},
        }
        if crop is None or crop.size == 0:
            return result
        h, w = crop.shape[:2]
        if h < 20 or w < 20:
            return result

        try:
            import cv2
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        except Exception as e:
            logger.debug(f"FacePoseAnalyzer[{self.camera_id}]: color conversion failed: {e}")
            return result

        if self._face_mesh is not None:
            try:
                face_result = self._face_mesh.process(rgb)
                if face_result.multi_face_landmarks:
                    lm = face_result.multi_face_landmarks[0].landmark
                    result["face_detected"] = True
                    result["ear"] = self._eye_aspect_ratio(lm, h, w)
                    result["mar"] = self._mouth_aspect_ratio(lm, h, w)
                    result["mouth_center"] = ((lm[_MOUTH_LEFT].x+lm[_MOUTH_RIGHT].x)/2,
                                              (lm[_MOUTH_TOP].y+lm[_MOUTH_BOTTOM].y)/2)
            except Exception as e:
                logger.debug(f"FacePoseAnalyzer[{self.camera_id}]: face mesh error: {e}")

        if self._pose is not None:
            try:
                pose_result = self._pose.process(rgb)
                if pose_result.pose_landmarks:
                    plm = pose_result.pose_landmarks.landmark
                    result['fight_wrists']={side:(float(plm[index].x),float(plm[index].y))
                        for side,index in (('left',15),('right',16))
                        if plm[index].visibility>=.6 and 0<=plm[index].x<=1 and 0<=plm[index].y<=1}
                    result['fall_pose']={key:(float(plm[index].x),float(plm[index].y))
                        for key,index in (('left_shoulder',11),('right_shoulder',12),('left_hip',23),('right_hip',24),('left_knee',25),('right_knee',26))
                        if plm[index].visibility>=.6 and 0<=plm[index].x<=1 and 0<=plm[index].y<=1}
                    result["pose_detected"] = True
                    result["head_down"] = self._head_down(plm)
                    result["facing_camera"] = self._facing_camera(plm)
                    for side, wrist, elbow, shoulder in (("left",15,13,11),("right",16,14,12)):
                        for key,index in (("wrists",wrist),("elbows",elbow),("shoulders",shoulder)):
                            landmark=plm[index]
                            result['landmark_visibility'][f'{side}_{key}']={'visibility':float(landmark.visibility),
                                'in_crop':bool(0<=landmark.x<=1 and 0<=landmark.y<=1)}
                            if key=='wrists':
                                result.setdefault('eating_wrist_candidates',{})[side]={
                                    'point':(float(landmark.x),float(landmark.y)),
                                    'visibility':float(landmark.visibility)}
                            if landmark.visibility >= .6 and 0 <= landmark.x <= 1 and 0 <= landmark.y <= 1:
                                result[key][side]=(landmark.x,landmark.y)
                                if key=='wrists':result['wrist_sources'][side]='pose'
            except Exception as e:
                logger.debug(f"FacePoseAnalyzer[{self.camera_id}]: pose error: {e}")

        if len(result['wrists'])<2 and getattr(self,'_hands',None) is not None:
            try:
                hand_result=self._hands.process(rgb)
                for landmarks,handedness in zip(hand_result.multi_hand_landmarks or [],hand_result.multi_handedness or []):
                    classification=handedness.classification[0]
                    side='right' if classification.label.lower()=='left' else 'left'
                    wrist=landmarks.landmark[0]
                    if classification.score>=.6 and side not in result['wrists'] and 0<=wrist.x<=1 and 0<=wrist.y<=1:
                        result['wrists'][side]=(wrist.x,wrist.y);result['wrist_sources'][side]='hands'
                        result['landmark_visibility'][f'{side}_hand_wrist']={'visibility':float(classification.score),'in_crop':True}
            except Exception as error:
                logger.debug(f'Hand landmark sample unavailable: {type(error).__name__}')
        return result

    # ─── Geometry helpers ────────────────────────────────────────────────────

    def analyze_activity_limbs(self, crop, wrist_visibility=.60):
        """Wider limb recovery using cached models; existing face rules are untouched."""
        import cv2
        result={'wrists':{},'elbows':{},'shoulders':{},'landmark_visibility':{},'wrist_sources':{}}
        if crop is None or crop.size==0:return result
        rgb=cv2.cvtColor(crop,cv2.COLOR_BGR2RGB)
        if self._pose is not None:
            pose=self._pose.process(rgb)
            if pose.pose_landmarks:
                landmarks=pose.pose_landmarks.landmark
                for side,wrist,elbow,shoulder in (('left',15,13,11),('right',16,14,12)):
                    for key,index in (('wrists',wrist),('elbows',elbow),('shoulders',shoulder)):
                        p=landmarks[index];inside=0<=p.x<=1 and 0<=p.y<=1
                        result['landmark_visibility'][f'{side}_{key}']={'visibility':float(p.visibility),'in_crop':inside}
                        cutoff=wrist_visibility if key=='wrists' else .60
                        if inside and p.visibility>=cutoff:
                            result[key][side]=(p.x,p.y)
                            if key=='wrists':result['wrist_sources'][side]='pose'
        if len(result['wrists'])<2 and getattr(self,'_hands',None) is not None:
            hands=self._hands.process(rgb)
            for landmarks,handedness in zip(hands.multi_hand_landmarks or [],hands.multi_handedness or []):
                classification=handedness.classification[0];p=landmarks.landmark[0]
                side='right' if classification.label.lower()=='left' else 'left'
                if classification.score>=.60 and side not in result['wrists'] and 0<=p.x<=1 and 0<=p.y<=1:
                    result['wrists'][side]=(p.x,p.y);result['wrist_sources'][side]='hands'
                    result['landmark_visibility'][f'{side}_hand_wrist']={'visibility':float(classification.score),
                        'in_crop':True,'confidence_kind':'handedness_score'}
        return result

    @staticmethod
    def _xy(landmarks, idx, h, w):
        p = landmarks[idx]
        return p.x * w, p.y * h

    def _eye_aspect_ratio(self, landmarks, h, w) -> float:
        def ear_for(idx6):
            p1 = self._xy(landmarks, idx6[0], h, w)
            p2 = self._xy(landmarks, idx6[1], h, w)
            p3 = self._xy(landmarks, idx6[2], h, w)
            p4 = self._xy(landmarks, idx6[3], h, w)
            p5 = self._xy(landmarks, idx6[4], h, w)
            p6 = self._xy(landmarks, idx6[5], h, w)
            vert = np.hypot(p2[0] - p6[0], p2[1] - p6[1]) + np.hypot(p3[0] - p5[0], p3[1] - p5[1])
            horiz = np.hypot(p1[0] - p4[0], p1[1] - p4[1])
            return (vert / (2.0 * horiz)) if horiz > 0 else 0.0

        return float((ear_for(_LEFT_EYE) + ear_for(_RIGHT_EYE)) / 2.0)

    def _mouth_aspect_ratio(self, landmarks, h, w) -> float:
        left = self._xy(landmarks, _MOUTH_LEFT, h, w)
        right = self._xy(landmarks, _MOUTH_RIGHT, h, w)
        top = self._xy(landmarks, _MOUTH_TOP, h, w)
        bottom = self._xy(landmarks, _MOUTH_BOTTOM, h, w)
        horiz = np.hypot(left[0] - right[0], left[1] - right[1])
        vert = np.hypot(top[0] - bottom[0], top[1] - bottom[1])
        return float(vert / horiz) if horiz > 0 else 0.0

    def _head_down(self, pose_landmarks) -> bool:
        """Nose at/below the shoulder line indicates a strongly bowed head."""
        nose_y = pose_landmarks[_POSE_NOSE].y
        shoulder_y = (pose_landmarks[_POSE_LEFT_SHOULDER].y + pose_landmarks[_POSE_RIGHT_SHOULDER].y) / 2.0
        return bool(nose_y >= shoulder_y - 0.03)

    def _facing_camera(self, pose_landmarks) -> bool:
        """Roughly symmetric, well-separated shoulders indicate the torso faces the camera."""
        left = pose_landmarks[_POSE_LEFT_SHOULDER]
        right = pose_landmarks[_POSE_RIGHT_SHOULDER]
        shoulder_width = abs(left.x - right.x)
        depth_diff = abs(left.z - right.z)
        return bool(shoulder_width > 0.08 and depth_diff < 0.15)
