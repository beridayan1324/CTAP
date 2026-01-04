// ===== ESP32 PIN CONFIG =====
// Fingers: 34, 35, 32, 33, 25
// Send/Space: 26
int piezoPins[] = {34, 35, 32, 33, 25, 26};  
int numPiezos = 6; 

int ledPin = 2;

// ===== SETTINGS =====
int thresholdDrop = 200;
int baseline = 800;
unsigned long debounceTime = 50;
unsigned long letterWait = 250; 

// ===== STATE =====
int lastReading[6] = {0};         
unsigned long lastHitTime[6] = {0}; 

// Track 5 fingers
bool fingerHit[5] = {false, false, false, false, false}; 
unsigned long firstHitTime = 0;

// Track consecutive space hits
int spaceHitCount = 0;

// Accumulated text message
String textSentence = "";

void setup() {
  Serial.begin(115200);
  pinMode(ledPin, OUTPUT);

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  Serial.println("CTAP 5-Finger Mode Ready");
  Serial.println("Pins: 34, 35, 32, 33, 25 (Fingers) | 26 (Send)");
}

void loop() {
  unsigned long now = millis();

  // --- read piezos ---
  for (int i = 0; i < numPiezos; i++) {
    int reading = analogRead(piezoPins[i]);
    int drop = lastReading[i] - reading;

    if (
      lastReading[i] >= baseline &&
      drop >= thresholdDrop &&
      (now - lastHitTime[i] > debounceTime)
    ) {
      lastHitTime[i] = now;
      digitalWrite(ledPin, !digitalRead(ledPin)); // Flash LED

      // Indices 0, 1, 2, 3, 4 are FINGERS (Pins 34, 35, 32, 33, 25)
      if (i < 5) {
        // --- FINGER HIT ---
        spaceHitCount = 0; // Reset space streak
        fingerHit[i] = true;
        if (firstHitTime == 0) firstHitTime = now;

      } else {
        // --- SPACE HIT (Index 5 -> Pin 26) ---
        spaceHitCount++;

        if (spaceHitCount >= 3) {
            // === SEND COMMAND (3x Space) ===
            textSentence.trim(); // Remove trailing spaces
            Serial.println(textSentence);
            
            // Reset
            textSentence = "";
            spaceHitCount = 0;
            resetFingers();
            
            // Long flash confirm
            digitalWrite(ledPin, HIGH); delay(200); digitalWrite(ledPin, LOW);
            return;
        } 
        else {
            // === STANDARD SPACE ===
            if (textSentence.length() > 0 && 
                textSentence[textSentence.length() - 1] != ' ') {
              textSentence += " ";
            }
        }
      }
    }
    lastReading[i] = reading;
  }

  // --- TRANSLATE and finish letter after timeout ---
  if (firstHitTime != 0 && (now - firstHitTime > letterWait)) {
    
    // 1. Build the binary string (e.g., "00101")
    String currentBits = "";
    for (int i = 0; i < 5; i++) {
      currentBits += fingerHit[i] ? "1" : "0";
    }

    // 2. Convert "00101" to letter
    String letter = getLetterFromBits(currentBits);

    // 3. Add to sentence
    if (letter != "") {
      textSentence += letter;
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
  
  if (bits == "11111") return "?"; 
  
  return ""; 
}

void resetFingers() {
  for (int i = 0; i < 5; i++) fingerHit[i] = false;
  firstHitTime = 0;
}