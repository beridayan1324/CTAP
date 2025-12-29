// ===== ESP32 PIN CONFIG =====
int piezoPins[] = {34, 35, 32, 33};  // 3 fingers + SEND (Space)
int numPiezos = 4;

int ledPin = 2;

// ===== SETTINGS =====
int thresholdDrop = 200;
int baseline = 800;
unsigned long debounceTime = 50;
unsigned long letterWait = 300; // Increased slightly to give time to hit multiple fingers

// ===== STATE =====
int lastReading[4] = {0};
unsigned long lastHitTime[4] = {0};

bool fingerHit[3] = {false, false, false};
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

  Serial.println("CTAP Text Translation Mode Ready");
  Serial.println("Mapping: 001=a, 010=b, 100=c, 101=d, etc.");
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

      if (i < 3) {
        // --- FINGER HIT ---
        spaceHitCount = 0; // Reset space streak
        fingerHit[i] = true;
        if (firstHitTime == 0) firstHitTime = now;

      } else {
        // --- SPACE HIT (Piezo 3) ---
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
            // Only add space if we have previous text and it's not already a space
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
    
    // 1. Build the binary string (e.g., "101")
    String currentBits = "";
    for (int i = 0; i < 3; i++) {
      currentBits += fingerHit[i] ? "1" : "0";
    }

    // 2. Convert "101" to "d"
    String letter = getLetterFromBits(currentBits);

    // 3. Add to sentence
    if (letter != "") {
      textSentence += letter;
      // Optional: Print partially built sentence to see progress
      // Serial.print("Current: "); Serial.println(textSentence); 
    }

    resetFingers();
  }

  delay(5);
}

// ===== DICTIONARY =====
// Change the letters here to customize your layout
String getLetterFromBits(String bits) {
  if (bits == "001") return "a";
  if (bits == "010") return "b";
  if (bits == "100") return "c";
  
  if (bits == "101") return "d"; 
  if (bits == "011") return "e"; 
  if (bits == "110") return "f"; 
  if (bits == "111") return "g"; 
  
  return ""; // Returns empty if 000
}

void resetFingers() {
  for (int i = 0; i < 3; i++) fingerHit[i] = false;
  firstHitTime = 0;
}