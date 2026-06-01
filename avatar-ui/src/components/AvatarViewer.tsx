import React from "react";
import { VRM, VRMHumanBoneName, VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

type ConcentrationState = "focused" | "distracted";

type AvatarViewerProps = {
  concentrationState: ConcentrationState;
  expressionOverride?: string;
  isSpeaking: boolean;
};

const AVATAR_URL = "/avatars/avatar.vrm";
const EXPRESSION_CANDIDATES = {
  neutral: ["neutral", "Neutral"],
  angry: ["angry", "Angry"],
  happy: ["happy", "joy", "Happy", "Joy"],
  fun: ["fun", "relaxed", "Fun", "Relaxed"],
};
const MOUTH_EXPRESSION_CANDIDATES = ["aa", "Aa", "AA", "A", "mouthOpen", "MouthOpen", "mouth_open"];

type LipSyncState = {
  mouthExpressionName?: string;
};

function setFirstAvailableExpression(vrm: VRM, candidates: string[], value: number) {
  const expressionManager = vrm.expressionManager;
  if (!expressionManager) {
    return;
  }

  const expressionName = candidates.find((candidate) => expressionManager.getExpression(candidate));
  if (expressionName) {
    expressionManager.setValue(expressionName, value);
  }
}

function resetAvailableExpressions(vrm: VRM, candidateGroups: string[][]) {
  const expressionManager = vrm.expressionManager;
  if (!expressionManager) {
    return;
  }

  candidateGroups.flat().forEach((candidate) => {
    if (expressionManager.getExpression(candidate)) {
      expressionManager.setValue(candidate, 0);
    }
  });
}

function getExpressionNameCandidates(expressionName: string) {
  return Array.from(new Set([expressionName, expressionName.toLowerCase(), expressionName.toUpperCase()]));
}

function getFirstAvailableExpressionName(vrm: VRM, candidates: string[]) {
  const expressionManager = vrm.expressionManager;
  if (!expressionManager) {
    return undefined;
  }

  return candidates.find((candidate) => expressionManager.getExpression(candidate));
}

function clampMouthOpenValue(value: number) {
  return Math.min(1, Math.max(0, value));
}

function calculateSimpleMouthOpenValue(elapsedTime: number) {
  const cycle = Math.sin(elapsedTime * 18);
  const normalized = (cycle + 1) / 2;
  return 0.18 + normalized * 0.72;
}

function setAvatarMouth(vrm: VRM, lipSyncState: LipSyncState, openValue: number) {
  const expressionManager = vrm.expressionManager;
  if (!expressionManager) {
    return;
  }

  const expressionName =
    lipSyncState.mouthExpressionName ?? getFirstAvailableExpressionName(vrm, MOUTH_EXPRESSION_CANDIDATES);
  if (!expressionName) {
    return;
  }

  lipSyncState.mouthExpressionName = expressionName;
  expressionManager.setValue(expressionName, clampMouthOpenValue(openValue));
  expressionManager.update();
}

export function setAvatarExpression(vrm: VRM, state: ConcentrationState, expressionOverride?: string) {
  const expressionManager = vrm.expressionManager;
  if (!expressionManager) {
    return;
  }

  resetAvailableExpressions(vrm, [
    EXPRESSION_CANDIDATES.neutral,
    EXPRESSION_CANDIDATES.angry,
    EXPRESSION_CANDIDATES.happy,
    EXPRESSION_CANDIDATES.fun,
  ]);

  if (state === "focused") {
    setFirstAvailableExpression(vrm, EXPRESSION_CANDIDATES.neutral, 0.35);
    setFirstAvailableExpression(vrm, EXPRESSION_CANDIDATES.angry, 0.45);
  } else {
    setFirstAvailableExpression(vrm, EXPRESSION_CANDIDATES.happy, 0.8);
    setFirstAvailableExpression(vrm, EXPRESSION_CANDIDATES.fun, 0.8);
  }

  if (expressionOverride) {
    setFirstAvailableExpression(vrm, getExpressionNameCandidates(expressionOverride), 1);
  }

  expressionManager.update();
}

function rotationArrayFromEuler(x: number, y: number, z: number) {
  return new THREE.Quaternion().setFromEuler(new THREE.Euler(x, y, z)).toArray() as [number, number, number, number];
}

function setAvatarArmPose(vrm: VRM) {
  vrm.humanoid.setNormalizedPose({
    [VRMHumanBoneName.LeftShoulder]: {
      rotation: rotationArrayFromEuler(0, 0, -0.16),
    },
    [VRMHumanBoneName.RightShoulder]: {
      rotation: rotationArrayFromEuler(0, 0, 0.16),
    },
    [VRMHumanBoneName.LeftUpperArm]: {
      rotation: rotationArrayFromEuler(0, 0, -1.18),
    },
    [VRMHumanBoneName.RightUpperArm]: {
      rotation: rotationArrayFromEuler(0, 0, 1.18),
    },
    [VRMHumanBoneName.LeftLowerArm]: {
      rotation: rotationArrayFromEuler(0, 0, -0.18),
    },
    [VRMHumanBoneName.RightLowerArm]: {
      rotation: rotationArrayFromEuler(0, 0, 0.18),
    },
  });
  vrm.humanoid.update();
}

function AvatarViewerComponent({ concentrationState, expressionOverride, isSpeaking }: AvatarViewerProps) {
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const vrmRef = React.useRef<VRM | null>(null);
  const concentrationStateRef = React.useRef(concentrationState);
  const expressionOverrideRef = React.useRef(expressionOverride);
  const isSpeakingRef = React.useRef(isSpeaking);
  const [loadState, setLoadState] = React.useState<"loading" | "ready" | "error">("loading");
  const [errorMessage, setErrorMessage] = React.useState("");

  React.useEffect(() => {
    concentrationStateRef.current = concentrationState;
  }, [concentrationState]);

  React.useEffect(() => {
    expressionOverrideRef.current = expressionOverride;
  }, [expressionOverride]);

  React.useEffect(() => {
    isSpeakingRef.current = isSpeaking;
    if (!isSpeaking && vrmRef.current) {
      setAvatarMouth(vrmRef.current, {}, 0);
    }
  }, [isSpeaking]);

  React.useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const scene = new THREE.Scene();
    scene.background = null;

    const camera = new THREE.PerspectiveCamera(24, 1, 0.1, 100);
    camera.position.set(0, 1.42, 1.85);

    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      preserveDrawingBuffer: true,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(renderer.domElement);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.72);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0xfff4e8, 1.15);
    keyLight.position.set(2.6, 3.4, 3.2);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0xcfe9e3, 0.42);
    fillLight.position.set(-3.2, 2.2, 2.6);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xf6d0b8, 0.28);
    rimLight.position.set(0, 2.2, -4);
    scene.add(rimLight);

    let animationFrame = 0;
    let isMounted = true;
    const clock = new THREE.Clock();
    const lipSyncState: LipSyncState = {};

    const resize = () => {
      const { width, height } = container.getBoundingClientRect();
      const nextWidth = Math.max(1, Math.floor(width));
      const nextHeight = Math.max(1, Math.floor(height));
      renderer.setSize(nextWidth, nextHeight, false);
      camera.aspect = nextWidth / nextHeight;
      camera.updateProjectionMatrix();
    };

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);
    resize();

    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    setLoadState("loading");
    setErrorMessage("");

    loader.load(
      AVATAR_URL,
      (gltf) => {
        if (!isMounted) {
          const loadedVrm = gltf.userData.vrm as VRM | undefined;
          if (loadedVrm) {
            VRMUtils.deepDispose(loadedVrm.scene);
          }
          return;
        }

        const vrm = gltf.userData.vrm as VRM | undefined;
        if (!vrm) {
          setErrorMessage("VRMデータを読み取れませんでした。");
          setLoadState("error");
          return;
        }

        VRMUtils.rotateVRM0(vrm);
        vrm.scene.position.set(0, 0, 0);
        vrm.scene.rotation.set(0, 0, 0);

        scene.add(vrm.scene);
        vrmRef.current = vrm;
        setAvatarArmPose(vrm);
        setAvatarExpression(vrm, concentrationStateRef.current, expressionOverrideRef.current);
        setAvatarMouth(vrm, lipSyncState, 0);

        const bounds = new THREE.Box3().setFromObject(vrm.scene);
        const size = bounds.getSize(new THREE.Vector3());
        const center = bounds.getCenter(new THREE.Vector3());
        const avatarHeight = Math.max(size.y, 1.5);
        const targetY = bounds.min.y + avatarHeight * 0.88;

        vrm.scene.position.x -= center.x;
        vrm.scene.position.z -= center.z;
        camera.position.set(0, targetY, avatarHeight * 1.28);
        camera.lookAt(0, targetY, 0);
        camera.updateProjectionMatrix();

        setLoadState("ready");
      },
      undefined,
      (error) => {
        if (!isMounted) {
          return;
        }
        console.error("Failed to load VRM avatar:", error);
        setErrorMessage("アバタの読み込みに失敗しました。public/avatars/avatar.vrm を確認してください。");
        setLoadState("error");
      },
    );

    const animate = () => {
      const delta = clock.getDelta();
      const elapsedTime = clock.elapsedTime;
      const vrm = vrmRef.current;

      if (vrm) {
        const mouthOpenValue = isSpeakingRef.current ? calculateSimpleMouthOpenValue(elapsedTime) : 0;
        setAvatarMouth(vrm, lipSyncState, mouthOpenValue);
        vrm.update(delta);
      }

      renderer.render(scene, camera);
      animationFrame = window.requestAnimationFrame(animate);
    };
    animate();

    return () => {
      isMounted = false;
      window.cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
      if (vrmRef.current) {
        scene.remove(vrmRef.current.scene);
        VRMUtils.deepDispose(vrmRef.current.scene);
      }
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
      vrmRef.current = null;
    };
  }, []);

  React.useEffect(() => {
    if (vrmRef.current) {
      setAvatarExpression(vrmRef.current, concentrationState, expressionOverride);
    }
  }, [concentrationState, expressionOverride]);

  return (
    <div className={`avatar-viewer ${concentrationState}`} data-testid="avatar-viewer" ref={containerRef} aria-label="3Dアバタ表示">
      <div className="avatar-viewer-glow" aria-hidden="true" />
      {loadState === "loading" && <div className="avatar-viewer-message">Loading avatar...</div>}
      {loadState === "error" && <div className="avatar-viewer-message error">{errorMessage}</div>}
    </div>
  );
}

export const AvatarViewer = React.memo(AvatarViewerComponent);
