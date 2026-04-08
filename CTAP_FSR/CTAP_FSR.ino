// ===== ESP32 PIN CONFIG =====
// Fingers: 34, 35, 32, 33, 25
int fsrPins[] = {34, 35, 32, 33, 25};
int numFSRs = 5;

int ledPin = 2;

// ===== SETTINGS =====
// FSRs read HIGH when pressed (opposite of piezo)
// Adjust pressThreshold based on your FSR + voltage divider setup
int pressThreshold = 500;    // Reading ABOVE this = finger pressed
int releaseThreshold = 300;  // Reading BELOW this = finger released (hysteresis)
unsigned long debounceTime = 50;
unsigned long letterWait = 300; // slightly longer to comfortably hit all 5

// ===== STATE =====
bool fingerCurrentlyPressed[5] = {false};  // Is the FSR currently held down?
bool fingerHit[5] = {false};               // Was this finger pressed in this letter window?
unsigned long firstHitTime = 0;
unsigned long lastDebounce[5] = {0};

// Track consecutive all-fingers hits
int allFingersCount = 0;

// Accumulated text message
String textSentence = "";

void setup() {
  Serial.begin(115200);
  pinMode(ledPin, OUTPUT);

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  Serial.println("CTAP FSR 5-Finger Mode Ready");
  Serial.println("Pins: 34, 35, 32, 33, 25 (Fingers)");
}

void loop() {
  unsigned long now = millis();

  // --- Read FSRs ---
  for (int i = 0; i < numFSRs; i++) {
    int reading = analogRead(fsrPins[i]);

    // --- Detect PRESS (rising edge) ---
    if (!fingerCurrentlyPressed[i] &&
        reading > pressThreshold &&
        (now - lastDebounce[i] > debounceTime)) {

      lastDebounce[i] = now;
      fingerCurrentlyPressed[i] = true;
      digitalWrite(ledPin, !digitalRead(ledPin)); // Flash LED

      // --- FINGER PRESS ---
      fingerHit[i] = true;
      if (firstHitTime == 0) firstHitTime = now;
    }

    // --- Detect RELEASE ---
    if (fingerCurrentlyPressed[i] && reading < releaseThreshold) {
      fingerCurrentlyPressed[i] = false;
    }
  }

  // --- TRANSLATE and finish letter after timeout ---
  if (firstHitTime != 0 && (now - firstHitTime > letterWait)) {

    // 1. Build binary string (e.g., "00101")
    String currentBits = "";
    for (int i = 0; i < 5; i++) {
      currentBits += fingerHit[i] ? "1" : "0";
    }

    // 2. Handle 5-finger action ("11111")
    if (currentBits == "11111") {
      allFingersCount++;
      
      if (allFingersCount >= 2) {
        // === SEND COMMAND (2x All Fingers) ===
        textSentence.trim();
        Serial.println(textSentence);

        // Reset
        textSentence = "";
        allFingersCount = 0;

        // Long flash to confirm send
        digitalWrite(ledPin, HIGH); delay(200); digitalWrite(ledPin, LOW);
      } else {
        // === STANDARD SPACE ===
        if (textSentence.length() > 0 &&
            textSentence[textSentence.length() - 1] != ' ') {
          textSentence += " ";
        }
      }
    } else {
      // It's a regular letter
      allFingersCount = 0;
      
      // 3. Convert bits to letter
      String letter = getLetterFromBits(currentBits);

      // 4. Add to sentence
      if (letter != "") {
        textSentence += letter;
      }
    }

    resetFingers();
  }

  delay(5);
}

// ===== DICTIONARY =====
// 5-bit Binary (Alphabetical Order A-Z)
String getLetterFromBits(String bits) {
  if (bits == "00001") return "a";
  if (bits == "00010") return "b";
  if (bits == "00011") return "c";
  if (bits == "00100") return "d";
  if (bits == "00101") return "e";
  if (bits == "00110") return "f";
  if (bits == "00111") return "g";
  if (bits == "01000") return "h";
  if (bits == "01001") return "i";
  if (bits == "01010") return "j";
  if (bits == "01011") return "k";
  if (bits == "01100") return "l";
  if (bits == "01101") return "m";
  if (bits == "01110") return "n";
  if (bits == "01111") return "o";
  if (bits == "10000") return "p";
  if (bits == "10001") return "q";
  if (bits == "10010") return "r";
  if (bits == "10011") return "s";
  if (bits == "10100") return "t";
  if (bits == "10101") return "u";
  if (bits == "10110") return "v";
  if (bits == "10111") return "w";
  if (bits == "11000") return "x";
  if (bits == "11001") return "y";
  if (bits == "11010") return "z";

  return "";
}

void resetFingers() {
  for (int i = 0; i < 5; i++) fingerHit[i] = false;
  firstHitTime = 0;
}
