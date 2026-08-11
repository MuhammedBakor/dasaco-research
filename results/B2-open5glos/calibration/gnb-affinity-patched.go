package gnb

import (
	"fmt"
	"log"
	"net"
	"sync"

	"github.com/free5gc/ngap"
	"github.com/free5gc/ngap/ngapType"
	ngapconn "github.com/hasukiHT/5glos/internal/ngap"
	"github.com/hasukiHT/5glos/internal/ue"
	"github.com/hasukiHT/5glos/internal/utils"
)

// Interfaces to avoid circular dependencies
type AMFInterface interface {
	SendNgap(pdu []byte) error
	GetId() string
}

type AMFManagerInterface interface {
	Pick() AMFInterface
}

type ServiceInterface interface {
	CreateUeContext(amf interface{}, gnb interface{}, ranUeNgapId int64) *ue.Context
	FindUeCtxByRanUeId(gnb interface{}, ranUeNgapId int64) *ue.Context
}

type Gnb struct {
	conn       *ngapconn.NgapConn
	ueList     map[int64]*ue.Context
	mutex      sync.Mutex
	name       string
	amfManager AMFManagerInterface // Dependency for AMF selection
	service    ServiceInterface    // Dependency for UE context creation
}

func New(name string) *Gnb {
	return &Gnb{
		ueList: make(map[int64]*ue.Context),
		name:   name,
	}
}

// Setter methods for dependency injection
func (gnb *Gnb) SetAMFManager(amfManager AMFManagerInterface) {
	gnb.amfManager = amfManager
}

func (gnb *Gnb) SetService(service ServiceInterface) {
	gnb.service = service
}

// Add UeContext
func (gnb *Gnb) Add(ueCtx *ue.Context) {
	gnb.mutex.Lock()
	defer gnb.mutex.Unlock()
	gnb.ueList[ueCtx.GetGnbUeId()] = ueCtx
}

// Create a GnB and start a goroutine to read data from its connection
func Create(conn net.Conn, wg *sync.WaitGroup) *Gnb {
	// Create GnB
	gnb := New(fmt.Sprintf("GnB-%v", conn.RemoteAddr()))

	// Create SCTP connection wrapper
	ngapConn := ngapconn.NewNgapConn(conn, gnb.handle)
	gnb.conn = ngapConn

	// Listen to NGAP messages from GnB
	wg.Add(1)
	go ngapConn.ReadLoop(wg)

	return gnb
}

func (gnb *Gnb) handle(msg *ngapconn.NgapMessage) error {
	switch msg.Present {
	case ngapType.NGAPPDUPresentInitiatingMessage:
		initiatingMessage := msg.InitiatingMessage
		if initiatingMessage == nil {
			return fmt.Errorf("InitiatingMessage is nil")
		}

		switch initiatingMessage.ProcedureCode.Value {
		case ngapType.ProcedureCodeNGSetup:
			log.Printf("[INFO] Handling NGSetupRequest from RAN %s", gnb.name)
			return gnb.handleNGSetupRequest(initiatingMessage)
		case ngapType.ProcedureCodeInitialUEMessage:
			log.Printf("[INFO] Handling Initial UE Message from RAN %s", gnb.name)
			return gnb.handleInitialUEMessage(initiatingMessage)
		case ngapType.ProcedureCodeUplinkNASTransport:
			log.Printf("[INFO] Handling Uplink NAS Transport from RAN %s", gnb.name)
			return gnb.handleUplinkNASTransport(initiatingMessage)
		case ngapType.ProcedureCodeAMFConfigurationUpdate:
			log.Printf("[INFO] Received AMF Configuration Update from RAN %s", gnb.name)
		case ngapType.ProcedureCodeAMFStatusIndication:
			log.Printf("[INFO] Received AMFStatusIndication from RAN %s", gnb.name)
		case ngapType.ProcedureCodeDownlinkNonUEAssociatedNRPPaTransport:
			log.Printf("[INFO] Received Downlink Non-UE Associated NRPPa Transport from RAN %s", gnb.name)
		case ngapType.ProcedureCodeDownlinkRANConfigurationTransfer:
			log.Printf("[INFO] Received Downlink RAN Configuration Transfer from RAN %s", gnb.name)
		case ngapType.ProcedureCodeOverloadStart:
			log.Printf("[INFO] Received Overload Start from RAN %s", gnb.name)
		case ngapType.ProcedureCodeOverloadStop:
			log.Printf("[INFO] Received Overload Stop from RAN %s", gnb.name)
		case ngapType.ProcedureCodePWSCancel:
			log.Printf("[INFO] Received PWS Cancel from RAN %s", gnb.name)
		case ngapType.ProcedureCodePWSFailureIndication:
			log.Printf("[INFO] Received PWS Failure Indication from RAN %s", gnb.name)
		case ngapType.ProcedureCodePWSRestartIndication:
			log.Printf("[INFO] Received PWS Restart Indication from RAN %s", gnb.name)
		case ngapType.ProcedureCodePaging:
			log.Printf("[INFO] Received Paging from RAN %s", gnb.name)
		case ngapType.ProcedureCodeRANConfigurationUpdate:
			log.Printf("[INFO] Received RAN Configuration Update from RAN %s", gnb.name)
		case ngapType.ProcedureCodeUplinkNonUEAssociatedNRPPaTransport:
			// handlerIgnoreMessage(initiatingMessage)
			log.Printf("[INFO] Received Uplink Non-UE Associated NRPPa Transport from RAN %s", gnb.name)
		case ngapType.ProcedureCodeUplinkRANConfigurationTransfer:
			log.Printf("[INFO] Received Uplink RAN Configuration Transfer from RAN %s", gnb.name)
		case ngapType.ProcedureCodeWriteReplaceWarning:
			log.Printf("[INFO] Received Write Replace Warning from RAN %s", gnb.name)
		default:
			// Forward other messages to AMF
			return gnb.forwardToAMF(msg)
		}

	case ngapType.NGAPPDUPresentSuccessfulOutcome:
		successfulOutcome := msg.SuccessfulOutcome
		if successfulOutcome == nil {
			return fmt.Errorf("SuccessfulOutcome is nil")
		}
		switch successfulOutcome.ProcedureCode.Value {
		case ngapType.ProcedureCodeAMFConfigurationUpdate:
			log.Printf("[INFO] Received AMF Configuration Update Acknowledge from RAN %s", gnb.name)
		case ngapType.ProcedureCodePWSCancel:
			// handlerIgnoreMessage(successfulOutcome)
			log.Printf("[INFO] Received PWS Cancel Acknowledge from RAN %s", gnb.name)
		case ngapType.ProcedureCodeRANConfigurationUpdate:
			// handlerIgnoreMessage(successfulOutcome)
			log.Printf("[INFO] Received RAN Configuration Update Acknowledge from RAN %s", gnb.name)
		case ngapType.ProcedureCodeWriteReplaceWarning:
			// handlerIgnoreMessage(successfulOutcome)
			log.Printf("[INFO] Received Write Replace Warning from RAN %s", gnb.name)
		default:
			// Forward other messages to AMF
			return gnb.forwardToAMF(msg)
		}

	case ngapType.NGAPPDUPresentUnsuccessfulOutcome:
		unsuccessfulOutcome := msg.UnsuccessfulOutcome
		if unsuccessfulOutcome == nil {
			return fmt.Errorf("UnsuccessfulOutcome is nil")
		}
		switch unsuccessfulOutcome.ProcedureCode.Value {
		case ngapType.ProcedureCodeAMFConfigurationUpdate:
			log.Printf("[INFO] Received AMF Configuration Update Failure from AMF %s", gnb.name)
		case ngapType.ProcedureCodeRANConfigurationUpdate:
			// handlerIgnoreMessage(unsuccessfulOutcome)
			log.Printf("[INFO] Received RAN Configuration Update Failure from AMF %s", gnb.name)
		default:
			// Forward other messages to AMF
			return gnb.forwardToAMF(msg)
		}

	}
	// Forward the original message as-is for unknown message types
	return gnb.forwardToAMF(msg)
}

func handlerIgnoreMessage(msg interface{}) {
	// Log the ignored message type for debugging purposes
	ngapMsg, ok := msg.(ngapType.NGAPPDU)
	var procCode int64 = -1
	if ok {
		switch ngapMsg.Present {
		case ngapType.NGAPPDUPresentInitiatingMessage:
			if ngapMsg.InitiatingMessage != nil {
				procCode = ngapMsg.InitiatingMessage.ProcedureCode.Value
			}
		case ngapType.NGAPPDUPresentSuccessfulOutcome:
			if ngapMsg.SuccessfulOutcome != nil {
				procCode = ngapMsg.SuccessfulOutcome.ProcedureCode.Value
			}
		case ngapType.NGAPPDUPresentUnsuccessfulOutcome:
			if ngapMsg.UnsuccessfulOutcome != nil {
				procCode = ngapMsg.UnsuccessfulOutcome.ProcedureCode.Value
			}
		}
		log.Printf("[INFO] Ignoring unknown message type: %T, Present: %v, Procedure Code: %d", msg, ngapMsg.Present, procCode)
	} else {
		log.Printf("[INFO] Ignoring unknown message type: %T (not NGAPPDU)", msg)
	}
	// Intentionally ignore the message (no-op)
}

func (gnb *Gnb) handleNGSetupRequest(initiatingMessage *ngapType.InitiatingMessage) error {
	// Send response locally using utils
	pkt, err := utils.BuildNGSetupResponse()
	if err != nil {
		return fmt.Errorf("build NGSetupResponse failed: %v", err)
	}

	if err := gnb.conn.SendNgap(pkt); err != nil {
		return fmt.Errorf("send NGSetupResponse failed: %v", err)
	}

	log.Printf("[INFO] Sent NGSetupResponse to GnB")
	return nil
}

func (gnb *Gnb) handleInitialUEMessage(initiatingMessage *ngapType.InitiatingMessage) error {
	// Extract RAN UE NGAP ID from message
	ranUeNgapId, _, found := utils.ExtractUeIdsFromMessage(&ngapType.NGAPPDU{
		Present:           ngapType.NGAPPDUPresentInitiatingMessage,
		InitiatingMessage: initiatingMessage,
	})

	if !found {
		log.Printf("[ERROR] Could not extract RAN UE NGAP ID from InitialUEMessage")
		ranUeNgapId = 1 // fallback
	}

	// Pick AMF using load balancing
	amf := gnb.amfManager.Pick()
	if amf == nil {
		return fmt.Errorf("no available AMF")
	}

	log.Printf("[INFO] Forwarding InitialUEMessage to AMF: %s", amf.GetId())

	// Create UE context - service will manage the mapping
	ueCtx := gnb.service.CreateUeContext(amf, gnb, ranUeNgapId)
	if ueCtx == nil {
		return fmt.Errorf("failed to create UE context")
	}

	// Forward message to AMF - the service will handle UE ID translation
	pdu := ngapType.NGAPPDU{
		Present:           ngapType.NGAPPDUPresentInitiatingMessage,
		InitiatingMessage: initiatingMessage,
	}
	log.Printf("[DEBUG] Replace RAN NGAP UE ID %d to LB NGAP UE ID %d", ranUeNgapId, ueCtx.GetLbId())
	// Modify the RAN UE NGAP ID to use our LB ID
	err := utils.ModifyUeIdsInMessage(&pdu, ueCtx.GetLbId(), ueCtx.GetAmfUeId())
	if err != nil {
		log.Printf("[WARN] Could not modify UE IDs, using original message: %v", err)
	}

	encoded, err := ngap.Encoder(pdu)
	if err != nil {
		return fmt.Errorf("encode message failed: %v", err)
	}

	log.Printf("[INFO] Successfully forwarded InitialUEMessage to AMF: %s", amf.GetId())
	return amf.SendNgap(encoded)
}

func (gnb *Gnb) handleUplinkNASTransport(initiatingMessage *ngapType.InitiatingMessage) error {
	// Forward message to AMF - the service will handle UE ID translation
	pdu := ngapType.NGAPPDU{
		Present:           ngapType.NGAPPDUPresentInitiatingMessage,
		InitiatingMessage: initiatingMessage,
	}

	// Extract RAN UE NGAP ID from message
	ranUeNgapId, amfUeNgapId, found := utils.ExtractUeIdsFromMessage(&pdu)

	if !found {
		log.Printf("[ERROR] Could not extract RAN UE NGAP ID from UplinkNASTransport")
		ranUeNgapId = 1 // fallback
		amfUeNgapId = 1 // fallback
	}

	// Find UE context using RAN UE NGAP ID
	ueCtx := gnb.service.FindUeCtxByRanUeId(gnb, ranUeNgapId)

	// Preserve UE-to-AMF affinity for the complete registration procedure.
	if ueCtx == nil {
		log.Printf("[ERROR] UE context not found for RAN UE NGAP ID: %d", ranUeNgapId)
		return fmt.Errorf("UE context not found")
	}

	destAmf, ok := ueCtx.GetAmf().(AMFInterface)
	if !ok || destAmf == nil {
		log.Printf("[ERROR] Stored AMF is unavailable for RAN UE NGAP ID: %d", ranUeNgapId)
		return fmt.Errorf("stored AMF unavailable")
	}

	// Replace UE IDs: use our internal IDs for communication with AMF
	// Use the LB ID as RAN UE NGAP ID and AMF UE NGAP ID from context
	newRanUeNgapId := ueCtx.GetLbId()    // Use LB ID as RAN UE NGAP ID for AMF
	newAmfUeNgapId := ueCtx.GetAmfUeId() // Use AMF UE NGAP ID from context

	log.Printf("[DEBUG] Replace RAN NGAP UE ID %d to LB NGAP UE ID %d", ranUeNgapId, newRanUeNgapId)
	log.Printf("[DEBUG] Replace LB NGAP UE ID %d to AMF NGAP UE ID %d", amfUeNgapId, newAmfUeNgapId)

	// Modify the RAN UE NGAP ID to use our LB ID
	err := utils.ModifyUeIdsInMessage(&pdu, newRanUeNgapId, newAmfUeNgapId)
	if err != nil {
		log.Printf("[WARN] Could not modify UE IDs, using original message: %v", err)
	}

	encoded, err := ngap.Encoder(pdu)
	if err != nil {
		return fmt.Errorf("encode message failed: %v", err)
	}

	log.Printf("[INFO] Forwarding message to AMF %s with modified UE IDs (Original RAN: %d, AMF: %d -> New RAN: %d, AMF: %d)",
		destAmf.GetId(), ranUeNgapId, amfUeNgapId, newRanUeNgapId, newAmfUeNgapId)

	return destAmf.SendNgap(encoded)
}

func (gnb *Gnb) forwardToAMF(msg *ngapconn.NgapMessage) error {
	// Validate the message structure
	if msg == nil {
		return fmt.Errorf("message is nil")
	}

	// Convert to NGAPPDU for processing
	ngapPdu := &ngapType.NGAPPDU{
		Present:             msg.Present,
		InitiatingMessage:   msg.InitiatingMessage,
		SuccessfulOutcome:   msg.SuccessfulOutcome,
		UnsuccessfulOutcome: msg.UnsuccessfulOutcome,
	}

	// Extract UE IDs from the original message
	ranUeNgapId, amfUeNgapId, found := utils.ExtractUeIdsFromMessage(ngapPdu)
	if !found {
		// If no UE IDs found, forward to any available AMF
		return gnb.forwardToAnyAMF(msg)
	}

	// Find UE context using RAN UE NGAP ID
	ueCtx := gnb.service.FindUeCtxByRanUeId(gnb, ranUeNgapId)
	if ueCtx == nil {
		log.Printf("[WARN] UE context not found for RAN UE NGAP ID: %d", ranUeNgapId)
		// If no UE context found, forward to any available AMF
		return gnb.forwardToAnyAMF(msg)
	}

	// Preserve UE-to-AMF affinity for every UE-associated NGAP message.
	destAmf, ok := ueCtx.GetAmf().(AMFInterface)
	if !ok || destAmf == nil {
		log.Printf("[ERROR] Stored AMF is unavailable for RAN UE NGAP ID: %d", ranUeNgapId)
		return fmt.Errorf("stored AMF unavailable")
	}

	// Create a copy of the message to modify
	msgCopy := *ngapPdu

	// Replace UE IDs: use our internal IDs for communication with AMF
	// Use the LB ID as RAN UE NGAP ID and AMF UE NGAP ID from context
	newRanUeNgapId := ueCtx.GetLbId()    // Use LB ID as RAN UE NGAP ID for AMF
	newAmfUeNgapId := ueCtx.GetAmfUeId() // Use AMF UE NGAP ID from context

	log.Printf("[DEBUG] Replace RAN NGAP UE ID %d to LB NGAP UE ID %d", ranUeNgapId, newRanUeNgapId)
	log.Printf("[DEBUG] Replace LB NGAP UE ID %d to AMF NGAP UE ID %d", amfUeNgapId, newAmfUeNgapId)
	err := utils.ModifyUeIdsInMessage(&msgCopy, newRanUeNgapId, newAmfUeNgapId)
	if err != nil {
		log.Printf("[ERROR] Failed to modify UE IDs in message: %v", err)
		// If modification fails, forward original message
		return gnb.forwardToSpecificAMF(msg, destAmf)
	}

	// log.Printf("[DEBUG] Message %+v", msgCopy)
	// Encode and forward the modified message
	pdu, err := ngap.Encoder(msgCopy)
	if err != nil {
		return fmt.Errorf("encode message failed: %v", err)
	}

	log.Printf("[INFO] Forwarding message to AMF %s with modified UE IDs (Original RAN: %d, AMF: %d -> New RAN: %d, AMF: %d)",
		destAmf.GetId(), ranUeNgapId, amfUeNgapId, newRanUeNgapId, newAmfUeNgapId)

	return destAmf.SendNgap(pdu)
}

// Helper method to forward to any available AMF (fallback)
func (gnb *Gnb) forwardToAnyAMF(msg *ngapconn.NgapMessage) error {
	amf := gnb.amfManager.Pick()
	if amf == nil {
		return fmt.Errorf("no available AMF")
	}

	return gnb.forwardToSpecificAMF(msg, amf)
}

// Helper method to forward to a specific AMF
func (gnb *Gnb) forwardToSpecificAMF(msg *ngapconn.NgapMessage, amf AMFInterface) error {
	pdu, err := ngap.Encoder(*msg)
	if err != nil {
		return fmt.Errorf("encode message failed: %v", err)
	}

	log.Printf("[INFO] Forwarding message to AMF: %s", amf.GetId())
	return amf.SendNgap(pdu)
}

func (gnb *Gnb) Close() {
	if gnb.conn != nil {
		gnb.conn.Close()
	}
}

// GetConn returns the underlying connection
func (gnb *Gnb) GetConn() net.Conn {
	if gnb.conn != nil {
		return gnb.conn.GetConn()
	}
	return nil
}

// SendNgap implements the interface for sending NGAP messages
func (gnb *Gnb) SendNgap(pdu []byte) error {
	if gnb.conn == nil {
		return fmt.Errorf("GnB connection is nil")
	}
	return gnb.conn.SendNgap(pdu)
}

// GetId returns the GnB identifier
func (gnb *Gnb) GetId() string {
	return gnb.name
}

// GetName returns the GnB name
func (gnb *Gnb) GetName() string {
	return gnb.name
}

// GetMutex returns the GnB mutex for external synchronization
func (gnb *Gnb) GetMutex() *sync.Mutex {
	return &gnb.mutex
}

// GetUeList returns the UE list for external access
func (gnb *Gnb) GetUeList() map[int64]*ue.Context {
	return gnb.ueList
}

// HasUeContext checks if the GnB has the specified UE context
func (gnb *Gnb) HasUeContext(ueCtx *ue.Context) bool {
	gnb.mutex.Lock()
	defer gnb.mutex.Unlock()

	_, exists := gnb.ueList[ueCtx.GetGnbUeId()]
	return exists
}
