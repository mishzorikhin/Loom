/* Гидрант.
   hydrantSvg(): красный гидрант с жёлтыми заглушками. */

function hydrantSvg() {
  return `${SHADOW_DOT("hysh", 8, 2.8)}
    <rect x="-3.4" y="-12" width="6.8" height="12" rx="1.4" fill="#ff6b57"/><rect x="0.6" y="-12" width="2.8" height="12" fill="#d9503f"/>
    <path d="M-3.8 -12 Q0 -17 3.8 -12 Z" fill="#ff8a76"/><rect x="-5.4" y="-8" width="2.4" height="3.4" rx="1" fill="#ffb347"/><rect x="3" y="-8" width="2.4" height="3.4" rx="1" fill="#e8962f"/>`;
}
