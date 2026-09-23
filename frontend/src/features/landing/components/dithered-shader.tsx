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
    const vec3 ink = vec3(0.02745, 0.03137, 0.06667);
    const vec3 midnight = vec3(0.10588, 0.12157, 0.19608);
    const vec3 slate = vec3(0.31373, 0.35686, 0.45490);
    const vec3 silver = vec3(0.69020, 0.72157, 0.74118);

    if (value < 0.34) {
      return mix(ink, midnight, value / 0.34);
    }

    if (value < 0.72) {
      return mix(midnight, slate, (value - 0.34) / 0.38);
    }

    return mix(slate, silver, (value - 0.72) / 0.28);
  }

  void main() {
    vec2 uv = gl_FragCoord.xy / u_resolution;
    vec2 point = (gl_FragCoord.xy - 0.5 * u_resolution) / min(u_resolution.x, u_resolution.y);
    float time = u_time * 0.1;
    vec2 driftA = vec2(time * 0.47, -time * 0.31);
    vec2 driftB = vec2(-time * 0.23, time * 0.41);

    vec2 warpA = vec2(
      fbm(point * 1.08 + driftA),
      fbm(point * 1.08 + vec2(5.2, -3.4) - driftA.yx)
    );
    vec2 silkPoint = point + (warpA - 0.5) * 0.58;

    vec2 warpB = vec2(
      fbm(silkPoint * 1.62 + driftB + vec2(2.1, 7.3)),
      fbm(silkPoint * 1.62 - driftB.yx + vec2(-4.7, 1.8))
    );
    silkPoint += (warpB - 0.5) * 0.22;

    float broadFlow = fbm(silkPoint * 0.78 + driftB * 0.62);
    float fineFlow = fbm(silkPoint * 1.74 - driftA * 0.38 + vec2(8.1, 3.7));

    float phaseA = silkPoint.x * 3.15 + silkPoint.y * 1.42;
    phaseA += (fineFlow - 0.5) * 5.8 + time * 0.52;
    float phaseB = -silkPoint.x * 1.55 + silkPoint.y * 3.72;
    phaseB += (broadFlow - 0.5) * 4.6 - time * 0.37;
    float phaseC = (silkPoint.x + silkPoint.y) * 2.28;
    phaseC += (warpA.x - warpB.y) * 4.2 + time * 0.21;

    float foldA = pow(1.0 - abs(sin(phaseA)), 3.1);
    float foldB = pow(1.0 - abs(sin(phaseB)), 3.8);
    float crossing = 0.5 + 0.5 * sin(phaseC);

    float light = 0.025;
    light += broadFlow * 0.27;
    light += fineFlow * 0.1;
    light += foldA * 0.24;
    light += foldB * 0.15;
    light += foldA * foldB * 0.2;
    light += crossing * 0.065;

    float quietEdge = smoothstep(0.58, 1.05, length(point * vec2(0.72, 0.92)));
    light *= 1.0 - quietEdge * 0.18;
    light = pow(clamp(light, 0.0, 1.0), 1.12);

    vec2 ditherCoordinate = gl_FragCoord.xy / max(1.0, u_pixel_ratio * u_dither_size);
    float threshold = bayer8(ditherCoordinate) - 0.5;
    float levels = 11.0;
    light = floor(clamp(light, 0.0, 1.0) * levels + 0.5 + threshold * 1.15) / levels;

    vec3 color = palette(clamp(light, 0.0, 1.0));
    float vignette = smoothstep(0.46, 0.9, distance(uv, vec2(0.5)));
    color *= 1.0 - vignette * 0.22;

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
    const positionBuffer = gl.createBuffer();

    if (
      positionLocation < 0 ||
      !resolutionLocation ||
      !timeLocation ||
      !pixelRatioLocation ||
      !ditherSizeLocation ||
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
    const startedAt = performance.now();
    let animationFrame: number | null = null;
    let isVisible = true;
    let isPageVisible = !document.hidden;

    const draw = (timestamp: number) => {
      animationFrame = null;
      gl.uniform1f(timeLocation, (timestamp - startedAt) / 1000);
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
      const bounds = container.getBoundingClientRect();
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
      gl.uniform1f(ditherSizeLocation, bounds.width < 640 ? 1.8 : 2.4);

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

    resizeObserver.observe(container);
    intersectionObserver.observe(container);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    reducedMotion.addEventListener("change", handleMotionPreference);
    resize();

    return () => {
      if (animationFrame !== null) {
        window.cancelAnimationFrame(animationFrame);
      }

      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      reducedMotion.removeEventListener("change", handleMotionPreference);
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
