#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>

const char* ssid = "Tejas's M35";
const char* password = "helloguy";

#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  10
#define SIOD_GPIO_NUM  40
#define SIOC_GPIO_NUM  39
#define Y9_GPIO_NUM    48
#define Y8_GPIO_NUM    11
#define Y7_GPIO_NUM    12
#define Y6_GPIO_NUM    14
#define Y5_GPIO_NUM    16
#define Y4_GPIO_NUM    18
#define Y3_GPIO_NUM    17
#define Y2_GPIO_NUM    15
#define VSYNC_GPIO_NUM 38
#define HREF_GPIO_NUM  47
#define PCLK_GPIO_NUM  13

const int MOTOR1_PIN = 1;
const int MOTOR2_PIN = 2;
const int MOTOR3_A = 3;
const int MOTOR3_B = 4;

const int PWM_FREQ = 5000;
const int PWM_RES = 8;

WebServer server(80);

void handleMotors() {
  int m1 = server.hasArg("m1") ? constrain(server.arg("m1").toInt(), 0, 255)    : 0;
  int m2 = server.hasArg("m2") ? constrain(server.arg("m2").toInt(), 0, 255)    : 0;
  int m3 = server.hasArg("m3") ? constrain(server.arg("m3").toInt(), -255, 255) : 0;

  ledcWrite(MOTOR1_PIN, m1);
  ledcWrite(MOTOR2_PIN, m2);

  if (m3 >= 0) {
    ledcWrite(MOTOR3_A, m3);
    ledcWrite(MOTOR3_B, 0);
  }
  else {
    ledcWrite(MOTOR3_A, 0);
    ledcWrite(MOTOR3_B, -m3);
  }

  Serial.printf("M1:%d M2:%d M3:%d\n", m1, m2, m3);
  server.send(200, "text/plain", "OK");
}

void handleSnapshot() {
  camera_fb_t * fb = esp_camera_fb_get();

  if (!fb) {
    Serial.println("Frame capture failed.");
    server.send(503, "text/plain", "Camera error");
    return;
  }

  Serial.printf("Frame OK: %d bytes\n", fb->len);

  WiFiClient client = server.client();

  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.setContentLength(fb->len);
  // server.send(200, "image/jpeg", "");
  server.send(200, "application/octet-stream", "");

  client.write(fb->buf, fb->len);

  esp_camera_fb_return(fb);
}

void startCamera() {
  camera_config_t config = {};

  config.ledc_channel = LEDC_CHANNEL_1;
  config.ledc_timer   = LEDC_TIMER_1;

  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;

  config.pin_xclk  = XCLK_GPIO_NUM;
  config.pin_pclk  = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href  = HREF_GPIO_NUM;

  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;

  config.pin_pwdn  = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;

  config.pixel_format = PIXFORMAT_GRAYSCALE;
  config.frame_size = FRAMESIZE_QQVGA;
  config.jpeg_quality = 50;
  config.fb_count = 1;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  config.xclk_freq_hz = 10000000;

  esp_err_t err = esp_camera_init(&config);

  if (err != ESP_OK) {
    Serial.printf("Camera initialisation failed: 0x%x\n", err);
    return;
  }

  Serial.println("Camera OK.");

  camera_fb_t * fb = esp_camera_fb_get();
  if (fb) {
    Serial.printf("Warmup OK: %d bytes\n", fb->len);
    esp_camera_fb_return(fb);
  }
  else {
    Serial.println("Warmup capture failed.");
  }

  sensor_t * s = esp_camera_sensor_get();
  Serial.printf("Sensor PID: 0x%x\n", s->id.PID);

  s->set_brightness(s, 1);
  s->set_contrast(s, 1);
  s->set_saturation(s, 0);

  s->set_gain_ctrl(s, 1);
  s->set_exposure_ctrl(s, 1);
  s->set_awb_gain(s, 1);

  s->set_aec2(s, 1);
  s->set_ae_level(s, 0);

  s->set_gainceiling(s, (gainceiling_t)4);

  Serial.printf("Pixel format: %d\n", config.pixel_format);
}

void setup() {
  Serial.begin(112500);

  ledcAttach(MOTOR1_PIN, PWM_FREQ, PWM_RES);
  ledcAttach(MOTOR2_PIN, PWM_FREQ, PWM_RES);
  ledcAttach(MOTOR3_A, PWM_FREQ, PWM_RES);
  ledcAttach(MOTOR3_B, PWM_FREQ, PWM_RES);

  ledcWrite(MOTOR1_PIN, 0);
  ledcWrite(MOTOR2_PIN, 0);
  ledcWrite(MOTOR3_A, 0);
  ledcWrite(MOTOR3_B, 0);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nIP: %s\n", WiFi.localIP().toString().c_str());

  startCamera();
  delay(2000);

  server.on("/snapshot", HTTP_GET, handleSnapshot);
  server.on("/motors",   HTTP_GET, handleMotors);
  server.begin();
  Serial.println("Server on port 80.");

  if (psramFound()) {
    Serial.println("PSRAM found.");
  }
  else {
    Serial.println("PSRAM NOT found.");
  }
}

void loop() {
  server.handleClient();
  delay(1);
}
