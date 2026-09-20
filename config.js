/* 公开配置。构建时可用 GEEKBIRD_API_BASE_URL 指定独立测试接口。
 * 接收开关由业务后台管理；不要在此填写密码或密钥。
 */
window.GEEKBIRD_CONFIG = Object.freeze({
  schemaVersion: 2,
  bookingUrl: "/booking/",
  feedbackUrl: "/feedback/",
  apiBaseUrl: "https://47.120.64.37/api/v1",
  dataAdminUrl: "https://47.120.64.37/_gb-data/",
  emergencyQQ: "2657698039",
});
