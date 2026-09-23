"use client";

import { useEffect, useRef } from "react";

import styles from "./dithered-shader.module.scss";

const vertexShaderSource = `
  attribute vec2 a_position;

  void main() {
    gl_Position = vec4(a_position, 0.0, 1.0);
  }
`;

const fragmentShaderSource = `
  #ifdef GL_FRAGMENT_PRECISION_HIGH
    precision highp float;
  #else
    precision mediump float;
  #endif

  uniform vec2 u_resolution;
  uniform float u_time;
  uniform float u_pixel_ratio;
  uniform float u_dither_size;
  uniform vec2 u_pointer;
  uniform float u_pointer_strength;

  float hash(vec2 point) {
    return fract(sin(dot(point, vec2(127.1, 311.7))) * 43758.5453123);
  }

  float noise(vec2 point) {
    vec2 cell = floor(point);
    vec2 local = fract(point);
    local = local * local * (3.0 - 2.0 * local);

    float a = hash(cell);
    float b = hash(cell + vec2(1.0, 0.0));
    float c = hash(cell + vec2(0.0, 1.0));
    float d = hash(cell + vec2(1.0, 1.0));

    return mix(mix(a, b, local.x), mix(c, d, local.x), local.y);
  }

  float fbm(vec2 point) {
    float value = 0.0;
    float amplitude = 0.5;
    mat2 rotation = mat2(0.80, -0.60, 0.60, 0.80);

    for (int octave = 0; octave < 5; octave++) {
      value += noise(point) * amplitude;
      point = rotation * point * 2.02 + vec2(17.3, 9.2);
      amplitude *= 0.5;
    }

    return value;
  }

  vec2 slowPath(float time, float seed) {
    return vec2(
      noise(vec2(time * 0.73, seed)),
      noise(vec2(seed + 9.7, time * 0.61))
    ) - 0.5;
  }

  mat2 rotate2d(float angle) {
    float sine = sin(angle);
    float cosine = cos(angle);
    return mat2(cosine, -sine, sine, cosine);
  }

  float softMass(float field, float low, float high) {
    return smoothstep(low, high, field);
  }

  float softFold(float field, float center, float width) {
    return 1.0 - smoothstep(0.0, width, abs(field - center));
  }

  float bayer2(vec2 point) {
    vec2 bit = mod(point, 2.0);
    return 2.0 * bit.x + 3.0 * bit.y - 4.0 * bit.x * bit.y;
  }

  float bayer8(vec2 point) {
    vec2 pixel = floor(point);
    float low = bayer2(mod(pixel, 2.0));
    float middle = bayer2(mod(floor(pixel / 2.0), 2.0));
    float high = bayer2(mod(floor(pixel / 4.0), 2.0));
    return (16.0 * low + 4.0 * middle + high) / 64.0;
  }

  vec3 palette(float value) {
    const vec3 ink = vec3(0.006);
    const vec3 charcoal = vec3(0.044);
    const vec3 ash = vec3(0.278);
    const vec3 silver = vec3(0.79);

    if (value < 0.20) {
      return mix(ink, charcoal, value / 0.20);
    }

    if (value < 0.62) {
      return mix(charcoal, ash, (value - 0.20) / 0.42);
    }

    return mix(ash, silver, (value - 0.62) / 0.38);
  }

  void main() {
    vec2 uv = gl_FragCoord.xy / u_resolution;
    vec2 point = (gl_FragCoord.xy - 0.5 * u_resolution) / min(u_resolution.x, u_resolution.y);
    float time = u_time * 0.025;

    vec2 pointerPoint = (u_pointer * u_resolution - 0.5 * u_resolution) /
      min(u_resolution.x, u_resolution.y);
    vec2 toPointer = pointerPoint - point;
    float pointerDistance = length(toPointer);
    float pointerFalloff = (1.0 - smoothstep(0.04, 0.72, pointerDistance)) *
      u_pointer_strength;
    vec2 pointerBend = normalize(toPointer + vec2(0.0001)) * pointerFalloff * 0.055;

    vec2 pathA = slowPath(time, 2.4) * vec2(0.72, 0.94);
    vec2 pathB = slowPath(time * 0.83, 8.1) * vec2(0.88, 0.68);
    vec2 pathC = slowPath(time * 1.17, 14.6) * vec2(0.62, 0.82);

    float breatheA = mix(0.91, 1.08, noise(vec2(time * 0.43, 3.8)));
    float breatheB = mix(0.94, 1.06, noise(vec2(11.2, time * 0.36)));
    float breatheC = mix(0.90, 1.10, noise(vec2(time * 0.31, 18.7)));

    vec2 farPoint = rotate2d(-0.31) * (point + pointerBend * 0.22) * breatheA;
    vec2 middlePoint = rotate2d(0.19) * (point + pointerBend * 0.58) * breatheB;
    vec2 nearPoint = rotate2d(-0.08) * (point + pointerBend) * breatheC;

    vec2 farWarp = vec2(
      fbm(farPoint * 0.74 + pathB + vec2(1.7, 7.2)),
      fbm(farPoint * 0.74 - pathA.yx + vec2(-5.1, 2.3))
    ) - 0.5;
    vec2 middleWarp = vec2(
      fbm(middlePoint * 0.92 + pathC + vec2(8.6, -1.4)),
      fbm(middlePoint * 0.92 - pathB.yx + vec2(3.1, 11.8))
    ) - 0.5;
    vec2 nearWarp = vec2(
      fbm(nearPoint * 1.08 + pathA + vec2(-3.8, 5.7)),
      fbm(nearPoint * 1.08 - pathC.yx + vec2(12.4, 4.2))
    ) - 0.5;

    float farField = fbm(farPoint * 0.82 + farWarp * 0.72 + pathA);
    float middleField = fbm(middlePoint * 1.03 + middleWarp * 0.84 + pathB);
    float nearField = fbm(nearPoint * 1.24 + nearWarp * 0.92 + pathC);

    float farMass = softMass(farField, 0.34, 0.68);
    float middleMass = softMass(middleField, 0.38, 0.67);
    float nearMass = softMass(nearField, 0.42, 0.68);
    float middleFold = softFold(middleField, 0.57, 0.15);
    float nearFold = softFold(nearField, 0.61, 0.13);

    float overlap = middleMass * nearMass;
    float light = 0.012;
    light += farMass * 0.18;
    light += middleMass * 0.28;
    light += middleFold * middleMass * 0.22;
    light += nearMass * 0.16;
    light += nearFold * nearMass * 0.36;
    light += overlap * 0.12;
    light -= (1.0 - farMass) * (1.0 - middleMass) * 0.035;

    float quietEdge = smoothstep(0.58, 1.05, length(point * vec2(0.72, 0.92)));
    light *= 1.0 - quietEdge * 0.22;
    light = pow(clamp(light, 0.0, 1.0), 1.18);

    vec2 ditherCoordinate = gl_FragCoord.xy / max(1.0, u_pixel_ratio * u_dither_size);
    float threshold = bayer8(ditherCoordinate) - 0.5;
    float grain = hash(floor(ditherCoordinate) + vec2(31.7, 19.3)) - 0.5;
    float levels = 13.0;
    light = floor(clamp(light, 0.0, 1.0) * levels + 0.5 + threshold * 0.94 + grain * 0.38) / levels;

    vec3 color = palette(clamp(light, 0.0, 1.0));
    float vignette = smoothstep(0.44, 0.92, distance(uv, vec2(0.5)));
    color *= 1.0 - vignette * 0.30;

    gl_FragColor = vec4(color, 1.0);
  }
`;

function compileShader(
  gl: WebGLRenderingContext,
  type: number,
  source: string,
) {
  const shader = gl.createShader(type);

  if (!shader) {
    return null;
  }

  gl.shaderSource(shader, source);
  gl.compileShader(shader);

  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader);
    return null;
  }

  return shader;
}

export function DitheredShaderBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = canvas?.parentElement;

    if (!canvas || !container) {
      return;
    }

    const interactionSurface = container.parentElement ?? container;

    const gl = canvas.getContext("webgl", {
      alpha: false,
      antialias: false,
      depth: false,
      powerPreference: "high-performance",
      preserveDrawingBuffer: false,
      stencil: false,
    });

    if (!gl) {
      return;
    }

    const vertexShader = compileShader(gl, gl.VERTEX_SHADER, vertexShaderSource);
    const fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, fragmentShaderSource);

    if (!vertexShader || !fragmentShader) {
      return;
    }

    const program = gl.createProgram();

    if (!program) {
      gl.deleteShader(vertexShader);
      gl.deleteShader(fragmentShader);
      return;
    }

    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);

    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      gl.deleteProgram(program);
      gl.deleteShader(vertexShader);
      gl.deleteShader(fragmentShader);
      return;
    }

    const positionLocation = gl.getAttribLocation(program, "a_position");
    const resolutionLocation = gl.getUniformLocation(program, "u_resolution");
    const timeLocation = gl.getUniformLocation(program, "u_time");
    const pixelRatioLocation = gl.getUniformLocation(program, "u_pixel_ratio");
    const ditherSizeLocation = gl.getUniformLocation(program, "u_dither_size");
    const pointerLocation = gl.getUniformLocation(program, "u_pointer");
    const pointerStrengthLocation = gl.getUniformLocation(program, "u_pointer_strength");
    const positionBuffer = gl.createBuffer();

    if (
      positionLocation < 0 ||
      !resolutionLocation ||
      !timeLocation ||
      !pixelRatioLocation ||
      !ditherSizeLocation ||
      !pointerLocation ||
      !pointerStrengthLocation ||
      !positionBuffer
    ) {
      gl.deleteProgram(program);
      gl.deleteShader(vertexShader);
      gl.deleteShader(fragmentShader);
      return;
    }

    gl.useProgram(program);
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
      gl.STATIC_DRAW,
    );
    gl.enableVertexAttribArray(positionLocation);
    gl.vertexAttribPointer(positionLocation, 2, gl.FLOAT, false, 0, 0);

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");
    const startedAt = performance.now();
    let animationFrame: number | null = null;
    let isVisible = true;
    let isPageVisible = !document.hidden;
    let lastFrameAt = startedAt;
    const pointer = { x: 0.5, y: 0.5, strength: 0 };
    const pointerTarget = { x: 0.5, y: 0.5, strength: 0 };

    const draw = (timestamp: number) => {
      animationFrame = null;
      const deltaSeconds = Math.min(Math.max((timestamp - lastFrameAt) / 1000, 0), 0.1);
      const interpolation = 1 - Math.exp(-deltaSeconds * 4.5);
      pointer.x += (pointerTarget.x - pointer.x) * interpolation;
      pointer.y += (pointerTarget.y - pointer.y) * interpolation;
      pointer.strength += (pointerTarget.strength - pointer.strength) * interpolation;
      lastFrameAt = timestamp;

      gl.uniform1f(timeLocation, (timestamp - startedAt) / 1000);
      gl.uniform2f(pointerLocation, pointer.x, pointer.y);
      gl.uniform1f(pointerStrengthLocation, pointer.strength);
      gl.drawArrays(gl.TRIANGLES, 0, 6);

      if (!reducedMotion.matches && isVisible && isPageVisible) {
        animationFrame = window.requestAnimationFrame(draw);
      }
    };

    const start = () => {
      if (animationFrame === null && isVisible && isPageVisible) {
        animationFrame = window.requestAnimationFrame(draw);
      }
    };

    const resize = () => {
      const bounds = interactionSurface.getBoundingClientRect();
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      const width = Math.max(1, Math.round(bounds.width * pixelRatio));
      const height = Math.max(1, Math.round(bounds.height * pixelRatio));

      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
        gl.viewport(0, 0, width, height);
      }

      gl.uniform2f(resolutionLocation, width, height);
      gl.uniform1f(pixelRatioLocation, pixelRatio);
      gl.uniform1f(ditherSizeLocation, bounds.width < 640 ? 1.2 : 1.45);

      if (reducedMotion.matches) {
        draw(startedAt);
      } else {
        start();
      }
    };

    const resizeObserver = new ResizeObserver(resize);
    const intersectionObserver = new IntersectionObserver(([entry]) => {
      isVisible = entry?.isIntersecting ?? false;

      if (isVisible) {
        start();
      }
    });

    const handleVisibilityChange = () => {
      isPageVisible = !document.hidden;

      if (isPageVisible) {
        start();
      }
    };

    const handleMotionPreference = () => {
      if (reducedMotion.matches && animationFrame !== null) {
        window.cancelAnimationFrame(animationFrame);
        animationFrame = null;
        draw(startedAt);
      } else {
        start();
      }
    };

    const handlePointerMove = (event: PointerEvent) => {
      if (!finePointer.matches || reducedMotion.matches) {
        return;
      }

      const bounds = interactionSurface.getBoundingClientRect();
      pointerTarget.x = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
      pointerTarget.y = 1 - Math.min(1, Math.max(0, (event.clientY - bounds.top) / bounds.height));
      pointerTarget.strength = 1;
      start();
    };

    const handlePointerLeave = () => {
      pointerTarget.strength = 0;
    };

    resizeObserver.observe(container);
    intersectionObserver.observe(container);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    reducedMotion.addEventListener("change", handleMotionPreference);
    interactionSurface.addEventListener("pointermove", handlePointerMove, { passive: true });
    interactionSurface.addEventListener("pointerleave", handlePointerLeave);
    resize();

    return () => {
      if (animationFrame !== null) {
        window.cancelAnimationFrame(animationFrame);
      }

      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      reducedMotion.removeEventListener("change", handleMotionPreference);
      interactionSurface.removeEventListener("pointermove", handlePointerMove);
      interactionSurface.removeEventListener("pointerleave", handlePointerLeave);
      gl.deleteBuffer(positionBuffer);
      gl.deleteProgram(program);
      gl.deleteShader(vertexShader);
      gl.deleteShader(fragmentShader);
    };
  }, []);

  return (
    <div className={styles.effect} data-effect="dithered-flow" aria-hidden="true">
      <canvas className={styles.canvas} ref={canvasRef} />
    </div>
  );
}
