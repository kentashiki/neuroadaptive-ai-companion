import { mkdir, writeFile } from "node:fs/promises";
import { chromium } from "playwright-core";

const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const outputDir = "/private/tmp/neuroadaptive-avatar-ui";
const targetUrl = process.env.AVATAR_UI_URL ?? "http://127.0.0.1:5174/";

const viewports = [
  { name: "desktop", width: 1280, height: 860 },
  { name: "mobile", width: 390, height: 844 },
];

await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({
  executablePath: chromePath,
  headless: true,
});

try {
  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport });
    page.on("console", (message) => {
      if (message.type() === "error") {
        console.error(`${viewport.name} console error: ${message.text()}`);
      }
    });
    page.on("pageerror", (error) => {
      console.error(`${viewport.name} page error: ${error.message}`);
    });
    await page.goto(targetUrl, { waitUntil: "domcontentloaded" });
    await page.locator("[data-testid='avatar-viewer'] canvas").waitFor({ state: "attached", timeout: 10000 });
    await page.getByText("Loading avatar...", { exact: true }).waitFor({ state: "hidden", timeout: 30000 });

    const screenshot = await page.screenshot({ fullPage: false });
    await writeFile(`${outputDir}/${viewport.name}.png`, screenshot);

    const canvasCheck = await page.locator("[data-testid='avatar-viewer'] canvas").evaluate((source) => {
      const sampleCanvas = document.createElement("canvas");
      sampleCanvas.width = source.width;
      sampleCanvas.height = source.height;

      const context = sampleCanvas.getContext("2d", { willReadFrequently: true });
      if (!context) {
        return { ok: false, width: source.width, height: source.height, sampledPixels: 0, variedPixels: 0 };
      }

      context.drawImage(source, 0, 0);
      const { data } = context.getImageData(0, 0, sampleCanvas.width, sampleCanvas.height);
      const centerIndex = (Math.floor(sampleCanvas.height / 2) * sampleCanvas.width + Math.floor(sampleCanvas.width / 2)) * 4;
      const base = [data[centerIndex], data[centerIndex + 1], data[centerIndex + 2], data[centerIndex + 3]];
      let sampledPixels = 0;
      let variedPixels = 0;

      for (let y = 0; y < sampleCanvas.height; y += 12) {
        for (let x = 0; x < sampleCanvas.width; x += 12) {
          const index = (y * sampleCanvas.width + x) * 4;
          sampledPixels += 1;
          const delta =
            Math.abs(data[index] - base[0]) +
            Math.abs(data[index + 1] - base[1]) +
            Math.abs(data[index + 2] - base[2]) +
            Math.abs(data[index + 3] - base[3]);
          if (delta > 24) {
            variedPixels += 1;
          }
        }
      }

      return {
        ok: sampledPixels > 0 && variedPixels > 20,
        width: source.width,
        height: source.height,
        sampledPixels,
        variedPixels,
      };
    });

    if (!canvasCheck.ok) {
      throw new Error(`${viewport.name} canvas appears blank: ${JSON.stringify(canvasCheck)}`);
    }

    console.log(
      `${viewport.name}: ${canvasCheck.width}x${canvasCheck.height}, varied ${canvasCheck.variedPixels}/${canvasCheck.sampledPixels}, screenshot ${outputDir}/${viewport.name}.png`,
    );

    await page.close();
  }
} finally {
  await browser.close();
}
