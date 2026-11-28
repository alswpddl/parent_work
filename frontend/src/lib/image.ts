// 휴대폰 사진을 올리기 전에 줄이기: 긴 변 1200px, JPEG 82% → 보통 100~300KB
export async function shrinkImage(file: File, maxSide = 1200, quality = 0.82): Promise<string> {
  if (!/^image\//.test(file.type)) throw new Error("사진 파일만 올릴 수 있어요.");
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((ok, fail) => {
      const el = new Image();
      el.onload = () => ok(el);
      el.onerror = () => fail(new Error("사진을 열지 못했어요. 다른 사진을 골라 주세요."));
      el.src = url;
    });
    const scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
    const w = Math.max(1, Math.round(img.naturalWidth * scale));
    const h = Math.max(1, Math.round(img.naturalHeight * scale));
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const g = canvas.getContext("2d");
    if (!g) throw new Error("이 브라우저에서는 사진을 줄일 수 없어요.");
    g.fillStyle = "#fff"; // 투명 PNG도 흰 바탕으로
    g.fillRect(0, 0, w, h);
    g.drawImage(img, 0, 0, w, h);
    return canvas.toDataURL("image/jpeg", quality);
  } finally {
    URL.revokeObjectURL(url);
  }
}
